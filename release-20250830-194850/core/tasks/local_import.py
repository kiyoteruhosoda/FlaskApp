"""
ローカルファイル取り込みタスク
固定ディレクトリからファイルを走査し、メディアとして取り込む
"""

import os
import hashlib
import shutil
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS
from flask import current_app

from core.db import db
from core.models.photo_models import Media, Exif, PickerSelection, MediaItem, PhotoMetadata, VideoMetadata
from core.models.job_sync import JobSync
from core.models.picker_session import PickerSession
from core.utils import get_file_date_from_name, get_file_date_from_exif
from webapp.config import Config


# サポートするファイル拡張子
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.heic', '.heif'}
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.webm'}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS


def calculate_file_hash(file_path: str) -> str:
    """ファイルのSHA-256ハッシュを計算"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_image_dimensions(file_path: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """画像の幅、高さ、向きを取得"""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            
            # EXIF orientationを取得
            orientation = None
            if hasattr(img, '_getexif') and img._getexif() is not None:
                exif_dict = img._getexif()
                for tag, value in exif_dict.items():
                    if TAGS.get(tag) == 'Orientation':
                        orientation = value
                        break
            
            return width, height, orientation
    except Exception:
        return None, None, None


def extract_exif_data(file_path: str) -> Dict:
    """EXIFデータを抽出"""
    exif_data = {}
    try:
        with Image.open(file_path) as img:
            if hasattr(img, '_getexif') and img._getexif() is not None:
                exif_dict = img._getexif()
                
                for tag_id, value in exif_dict.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif_data[tag] = value
                    
    except Exception:
        pass
    
    return exif_data


def extract_video_metadata(file_path: str) -> Dict:
    """動画ファイルからメタデータを抽出（ffprobeを使用）"""
    metadata = {}
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(file_path)
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            info = json.loads(proc.stdout)
            
            # ビデオストリーム情報を取得
            video_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
            if video_streams:
                v_stream = video_streams[0]
                # FPSを取得
                if "r_frame_rate" in v_stream:
                    fps_str = v_stream["r_frame_rate"]
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        if den != "0":
                            metadata["fps"] = float(num) / float(den)
                    else:
                        metadata["fps"] = float(fps_str)
                
                # 幅・高さを取得
                metadata["width"] = v_stream.get("width")
                metadata["height"] = v_stream.get("height")
            
            # フォーマット情報から時間を取得
            format_info = info.get("format", {})
            if "duration" in format_info:
                metadata["duration_ms"] = int(float(format_info["duration"]) * 1000)
    
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, ValueError):
        # ffprobeが使えない場合やエラーの場合は空のメタデータを返す
        pass
    
    return metadata


def generate_filename(shot_at: datetime, file_extension: str, file_hash: str) -> str:
    """
    ファイル名を生成
    フォーマット: YYYYMMDD_HHMMSS_local_hash8.ext
    """
    date_str = shot_at.strftime("%Y%m%d_%H%M%S")
    hash8 = file_hash[:8]
    return f"{date_str}_local_{hash8}{file_extension}"


def get_relative_path(shot_at: datetime, filename: str) -> str:
    """相対パスを生成 (YYYY/MM/DD/filename)"""
    year = shot_at.strftime("%Y")
    month = shot_at.strftime("%m")
    day = shot_at.strftime("%d")
    return f"{year}/{month}/{day}/{filename}"


def check_duplicate_media(file_hash: str, file_size: int) -> Optional[Media]:
    """重複チェック: SHA-256 + サイズ一致"""
    return Media.query.filter_by(
        hash_sha256=file_hash,
        bytes=file_size
    ).first()


def create_media_item_for_local(filename: str, mime_type: str, width: Optional[int], height: Optional[int], 
                               is_video: bool, exif_data: Optional[Dict] = None, video_metadata: Optional[Dict] = None) -> MediaItem:
    """ローカルファイル用のMediaItemを作成"""
    import uuid
    
    # ファイル名からユニークなIDを生成
    media_item_id = f"local_{uuid.uuid4().hex[:16]}"
    
    # MediaItemタイプの決定
    item_type = "VIDEO" if is_video else "PHOTO"
    
    media_item = MediaItem(
        id=media_item_id,
        type=item_type,
        mime_type=mime_type,
        filename=filename,
        width=width,
        height=height,
        camera_make=exif_data.get('Make') if exif_data else None,
        camera_model=exif_data.get('Model') if exif_data else None
    )
    
    # メタデータの作成
    if is_video:
        # ビデオメタデータ（ffprobeから取得、取れない場合はNULL）
        video_meta = VideoMetadata(
            fps=video_metadata.get('fps') if video_metadata else None,
            processing_status='UNSPECIFIED'
        )
        db.session.add(video_meta)
        db.session.flush()  # IDを取得
        media_item.video_metadata_id = video_meta.id
    else:
        # フォトメタデータ（EXIFから取得、取れない場合はNULL）
        photo_meta = PhotoMetadata(
            focal_length=exif_data.get('FocalLength') if exif_data else None,
            aperture_f_number=exif_data.get('FNumber') if exif_data else None,
            iso_equivalent=exif_data.get('ISOSpeedRatings') if exif_data else None,
            exposure_time=str(exif_data.get('ExposureTime', '')) if exif_data and exif_data.get('ExposureTime') else None
        )
        db.session.add(photo_meta)
        db.session.flush()  # IDを取得
        media_item.photo_metadata_id = photo_meta.id
    
    db.session.add(media_item)
    return media_item


def import_single_file(file_path: str, import_dir: str, originals_dir: str) -> Dict:
    """
    単一ファイルの取り込み処理
    
    Returns:
        処理結果辞書
    """
    result = {
        "success": False,
        "file_path": file_path,
        "reason": "",
        "media_id": None
    }
    
    try:
        # ファイル存在チェック
        if not os.path.exists(file_path):
            result["reason"] = "ファイルが存在しません"
            return result
        
        # 拡張子チェック
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in SUPPORTED_EXTENSIONS:
            result["reason"] = f"サポートされていない拡張子: {file_extension}"
            return result
        
        # ファイルサイズとハッシュ計算
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            result["reason"] = "ファイルサイズが0です"
            return result
        
        file_hash = calculate_file_hash(file_path)
        
        # 重複チェック
        existing_media = check_duplicate_media(file_hash, file_size)
        if existing_media:
            result["reason"] = f"重複ファイル (既存ID: {existing_media.id})"
            return result
        
        # 撮影日時の取得
        shot_at = None
        
        # まずEXIFから取得を試行
        if file_extension in SUPPORTED_IMAGE_EXTENSIONS:
            exif_data = extract_exif_data(file_path)
            shot_at = get_file_date_from_exif(exif_data)
        
        # EXIFから取得できない場合は、ファイル名から取得
        if not shot_at:
            shot_at = get_file_date_from_name(os.path.basename(file_path))
        
        # それでも取得できない場合は、ファイルの更新日時を使用
        if not shot_at:
            mtime = os.path.getmtime(file_path)
            shot_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
        
        # ファイル名とパスの生成
        new_filename = generate_filename(shot_at, file_extension, file_hash)
        rel_path = get_relative_path(shot_at, new_filename)
        dest_path = os.path.join(originals_dir, rel_path)
        
        # ディレクトリ作成
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # メディア情報の取得
        is_video = file_extension in SUPPORTED_VIDEO_EXTENSIONS
        width, height, orientation = None, None, None
        duration_ms = None
        
        if not is_video:
            width, height, orientation = get_image_dimensions(file_path)
        else:
            # 動画の場合はffprobeで取得（後でvideo_metaに保存）
            pass
        
        # MIMEタイプの決定
        mime_type_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.tiff': 'image/tiff', '.tif': 'image/tiff',
            '.bmp': 'image/bmp', '.heic': 'image/heic', '.heif': 'image/heif',
            '.mp4': 'video/mp4', '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska',
            '.m4v': 'video/mp4', '.3gp': 'video/3gpp', '.webm': 'video/webm'
        }
        mime_type = mime_type_map.get(file_extension, 'application/octet-stream')
        
        # ファイルコピー
        shutil.copy2(file_path, dest_path)
        
        # EXIFデータと動画メタデータの事前取得（MediaItem作成で使用）
        exif_data = None
        video_meta = None
        if not is_video and file_extension in SUPPORTED_IMAGE_EXTENSIONS:
            exif_data = extract_exif_data(file_path)
        elif is_video:
            video_meta = extract_video_metadata(file_path)
            # 動画メタデータから寸法・時間を取得
            if video_meta:
                width = video_meta.get('width') or width
                height = video_meta.get('height') or height
                duration_ms = video_meta.get('duration_ms') or duration_ms
        
        # MediaItemとメタデータの作成
        media_item = create_media_item_for_local(
            filename=os.path.basename(file_path),
            mime_type=mime_type,
            width=width,
            height=height,
            is_video=is_video,
            exif_data=exif_data,
            video_metadata=video_meta
        )
        
        # DBへの登録
        media = Media(
            google_media_id=media_item.id,  # ローカルファイルの場合はmedia_item.idを使用
            account_id=None,                # ローカルファイルの場合はNone
            local_rel_path=rel_path,
            hash_sha256=file_hash,
            bytes=file_size,
            mime_type=mime_type,
            width=width,
            height=height,
            duration_ms=duration_ms,
            shot_at=shot_at,
            imported_at=datetime.now(timezone.utc),
            orientation=orientation,
            is_video=is_video,
            live_group_id=None,
            is_deleted=False,
            has_playback=False
        )
        
        db.session.add(media)
        db.session.flush()  # IDを取得
        
        # EXIFデータの保存（画像の場合、すでに取得済みのデータを使用）
        if not is_video and file_extension in SUPPORTED_IMAGE_EXTENSIONS and exif_data:
            exif = Exif(
                media_id=media.id,
                camera_make=exif_data.get('Make'),
                camera_model=exif_data.get('Model'),
                lens=exif_data.get('LensModel'),
                iso=exif_data.get('ISOSpeedRatings'),
                shutter=str(exif_data.get('ExposureTime', '')),
                f_number=exif_data.get('FNumber'),
                focal_len=exif_data.get('FocalLength'),
                gps_lat=exif_data.get('GPSLatitude'),
                gps_lng=exif_data.get('GPSLongitude'),
                raw_json=str(exif_data) if exif_data else None
            )
            db.session.add(exif)
        
        db.session.commit()
        
        # 元ファイルの削除
        os.remove(file_path)
        
        result["success"] = True
        result["media_id"] = media.id
        result["reason"] = "取り込み成功"
        
    except Exception as e:
        db.session.rollback()
        result["reason"] = f"エラー: {str(e)}"
        
        # コピー先ファイルが作成されていた場合は削除
        try:
            if 'dest_path' in locals() and os.path.exists(dest_path):
                os.remove(dest_path)
        except:
            pass
    
    return result


def scan_import_directory(import_dir: str) -> List[str]:
    """取り込みディレクトリをスキャンしてサポートファイルを取得"""
    files = []
    
    if not os.path.exists(import_dir):
        return files
    
    for root, dirs, filenames in os.walk(import_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            file_extension = Path(filename).suffix.lower()
            
            if file_extension in SUPPORTED_EXTENSIONS:
                files.append(file_path)
    
    return files


def local_import_task(task_instance=None, session_id=None) -> Dict:
    """
    ローカル取り込みタスクのメイン処理
    
    Args:
        task_instance: Celeryタスクインスタンス（進行状況報告用）
        session_id: API側で作成されたPickerSessionのID
    
    Returns:
        処理結果辞書
    """
    # Flaskアプリケーションのコンテキストから設定を取得
    try:
        import_dir = current_app.config.get('LOCAL_IMPORT_DIR', Config.LOCAL_IMPORT_DIR)
        originals_dir = current_app.config.get('FPV_NAS_ORIGINALS_DIR', Config.FPV_NAS_ORIGINALS_DIR)
    except RuntimeError:
        # Flaskアプリケーションコンテキスト外の場合は設定クラスから取得
        import_dir = Config.LOCAL_IMPORT_DIR
        originals_dir = Config.FPV_NAS_ORIGINALS_DIR
    
    result = {
        "ok": True,
        "processed": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "details": [],
        "session_id": session_id
    }
    
    # API側で作成されたセッションを取得
    session = None
    if session_id:
        try:
            session = PickerSession.query.filter_by(session_id=session_id).first()
            if not session:
                result["errors"].append(f"セッションが見つかりません: {session_id}")
                return result
        except Exception as e:
            result["errors"].append(f"セッション取得エラー: {str(e)}")
            return result
    else:
        # セッションIDが無い場合は新規セッションを作成
        session = PickerSession(
            session_id=uuid.uuid4().hex,
            status="processing",
            selected_count=0,
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.session_id
        result["session_id"] = session_id
    
    try:
        # ディレクトリの存在チェック
        if not os.path.exists(import_dir):
            # ディレクトリが存在しない場合も0件処理として完了扱い
            session.status = "imported"
            session.selected_count = 0
            session.updated_at = datetime.now(timezone.utc)
            session.last_progress_at = datetime.now(timezone.utc)
            
            # 統計情報を設定
            stats = {
                "total": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0
            }
            session.set_stats(stats)
            db.session.commit()
            
            result["errors"].append(f"取り込みディレクトリが存在しません: {import_dir}")
            return result
        
        if not os.path.exists(originals_dir):
            # 保存先ディレクトリが存在しない場合も0件処理として完了扱い
            session.status = "imported"
            session.selected_count = 0
            session.updated_at = datetime.now(timezone.utc)
            session.last_progress_at = datetime.now(timezone.utc)
            
            # 統計情報を設定
            stats = {
                "total": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0
            }
            session.set_stats(stats)
            db.session.commit()
            
            result["errors"].append(f"保存先ディレクトリが存在しません: {originals_dir}")
            return result
        
        # ファイル一覧の取得
        files = scan_import_directory(import_dir)
        
        # ファイルが0件でも正常処理として扱う
        total_files = len(files)
        
        if total_files == 0:
            # 0件処理として完了
            session.status = "imported"
            session.selected_count = 0
            session.updated_at = datetime.now(timezone.utc)
            session.last_progress_at = datetime.now(timezone.utc)
            
            # 統計情報を設定
            stats = {
                "total": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0
            }
            session.set_stats(stats)
            db.session.commit()
            
            result["errors"].append(f"取り込み対象ファイルが見つかりません: {import_dir}")
            return result
        
        # 進行状況の初期化
        if task_instance:
            task_instance.update_state(
                state='PROGRESS',
                meta={
                    'status': f'{total_files}個のファイルの取り込みを開始します',
                    'progress': 0,
                    'current': 0,
                    'total': total_files,
                    'message': '取り込み開始'
                }
            )
        
        # ファイルごとの処理
        for index, file_path in enumerate(files, 1):
            result["processed"] += 1
            filename = os.path.basename(file_path)
            
            # PickerSelectionレコードを作成（ローカルインポート用）
            selection = None
            if session:
                try:
                    selection = PickerSelection(
                        session_id=session.id,
                        google_media_id=None,  # ローカルファイルなのでNone
                        local_file_path=file_path,
                        local_filename=filename,
                        status="pending",
                        attempts=0,
                        enqueued_at=datetime.now(timezone.utc)
                    )
                    db.session.add(selection)
                    db.session.commit()
                except Exception as e:
                    current_app.logger.warning(f"Failed to create picker selection for {filename}: {e}")
            
            # 進行状況の更新
            if task_instance:
                progress = int((index / total_files) * 100)
                task_instance.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'ファイル処理中: {filename}',
                        'progress': progress,
                        'current': index,
                        'total': total_files,
                        'message': f'{index}/{total_files} 処理中'
                    }
                )
            
            # Selectionの状態を処理中に更新
            if selection:
                try:
                    selection.status = "running"
                    selection.started_at = datetime.now(timezone.utc)
                    db.session.commit()
                except Exception:
                    pass
            
            file_result = import_single_file(file_path, import_dir, originals_dir)
            
            # Selectionの状態を処理結果に応じて更新
            if selection:
                try:
                    if file_result["success"]:
                        selection.status = "imported"
                        selection.finished_at = datetime.now(timezone.utc)
                    elif "重複ファイル" in file_result["reason"]:
                        selection.status = "dup"
                        selection.finished_at = datetime.now(timezone.utc)
                    else:
                        selection.status = "failed"
                        selection.error = file_result["reason"]
                        selection.finished_at = datetime.now(timezone.utc)
                        selection.attempts = 1
                    db.session.commit()
                except Exception as e:
                    current_app.logger.warning(f"Failed to update picker selection for {filename}: {e}")
            
            # 詳細な結果を記録
            detail = {
                "file": filename,
                "status": "success" if file_result["success"] else "failed",
                "reason": file_result["reason"],
                "media_id": file_result.get("media_id")
            }
            result["details"].append(detail)
            
            if file_result["success"]:
                result["success"] += 1
            else:
                if "重複ファイル" in file_result["reason"]:
                    result["skipped"] += 1
                    detail["status"] = "skipped"
                    # 重複の場合も元ファイルを削除
                    try:
                        os.remove(file_path)
                    except:
                        pass
                else:
                    result["failed"] += 1
                    result["errors"].append(f"{file_path}: {file_result['reason']}")
        
        # 最終進行状況の更新
        if task_instance:
            task_instance.update_state(
                state='PROGRESS',
                meta={
                    'status': '取り込み完了',
                    'progress': 100,
                    'current': total_files,
                    'total': total_files,
                    'message': f'完了: 成功{result["success"]}, スキップ{result["skipped"]}, 失敗{result["failed"]}'
                }
            )
        
    except Exception as e:
        result["ok"] = False
        result["errors"].append(f"取り込み処理でエラーが発生しました: {str(e)}")
    
    # セッションステータスの更新
    if session:
        try:
            session.status = "imported" if result["ok"] and result["success"] > 0 else ("error" if not result["ok"] else "ready")
            session.selected_count = result["success"]
            session.updated_at = datetime.now(timezone.utc)
            session.last_progress_at = datetime.now(timezone.utc)
            
            # 統計情報を設定
            stats = {
                "total": result["processed"],
                "success": result["success"],
                "skipped": result["skipped"],
                "failed": result["failed"]
            }
            session.set_stats(stats)
            
            db.session.commit()
        except Exception as e:
            result["errors"].append(f"セッション更新エラー: {str(e)}")
    
    return result


if __name__ == "__main__":
    # テスト実行用
    from webapp import create_app
    
    app = create_app()
    with app.app_context():
        result = local_import_task()
        print(f"処理結果: {result}")
