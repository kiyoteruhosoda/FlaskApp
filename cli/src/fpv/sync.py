from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from .repo import (
    get_engine, get_active_accounts, create_job, finalize_job,
    media_exists_by_hash, insert_media, upsert_exif,
    upsert_media_playback_queue, update_job_stats, save_pagination_cursor,
)
from .logs import log, new_trace_id
from .config import PhotoNestConfig
from . import google
from .storage import download_to_tmp, sha256_of, decide_relpath, atomic_move
from .mimeutil import ext_from_filename, ext_from_mime, is_video_mime


def _parse_creation_time(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def run_sync(
    all_accounts: bool = True,
    account_id: Optional[int] = None,
    dry_run: bool = True,
    page_size: int = 50,
    max_pages: int = 1,
) -> int:
    """Synchronize media items from Google Photos.

    Parameters
    ----------
    all_accounts: bool
        Process all active accounts when ``True``.
    account_id: Optional[int]
        Target a single account when provided.
    dry_run: bool
        Skip downloads when ``True``.
    page_size: int
        Page size to request from the API.
    max_pages: int
        Maximum number of pages to retrieve.
    """
    trace = new_trace_id()
    eng = get_engine()
    cfg = PhotoNestConfig.from_env()

    accounts = get_active_accounts(eng, account_id=None if all_accounts else account_id)
    if not accounts:
        log("sync.no_accounts", trace=trace)
        return 0

    overall_failed = 0

    for acc in accounts:
        aid, email, enc = int(acc["id"]), acc["account_email"], acc["oauth_token_json"]
        log("sync.account.begin", trace=trace, account_id=aid, email=email, dry_run=dry_run)

        job_id = create_job(eng, account_id=aid, target="google_photos")
        stats: Dict[str, Any] = {"listed": 0, "new": 0, "dup": 0, "failed": 0}
        status = "success"

        try:
            if dry_run:
                for i in range(1, 4):
                    log("sync.dryrun.item", trace=trace, account_id=aid, idx=i)
                stats["listed"] = 3
            else:
                token, meta = google.refresh_access_token(
                    enc,
                    cfg.oauth_key,
                    cfg.google_client_id,
                    cfg.google_client_secret,
                )
                log(
                    "sync.token.ok",
                    trace=trace,
                    account_id=aid,
                    expires_in=meta.get("expires_in", 0),
                )

                page: Optional[str] = None
                pages_done = 0
                while True:
                    if pages_done >= max_pages:
                        break
                    try:
                        resp = google.list_media_items_once(token, page_size=page_size, page_token=page)
                    except google.GoogleAPIError as ge:
                        status = "failed"
                        stats["failed"] += 1
                        overall_failed += 1
                        log(
                            "sync.list.error",
                            trace=trace,
                            account_id=aid,
                            status=ge.status,
                            message=str(ge),
                        )
                        break

                    items = resp.get("mediaItems") or []
                    next_token = resp.get("nextPageToken")
                    stats["listed"] += len(items)
                    update_job_stats(eng, job_id, listed=len(items))
                    save_pagination_cursor(eng, job_id, next_token)

                    if not items:
                        break

                    for it in items:
                        try:
                            mid = it.get("id")
                            mime = (it.get("mimeType") or "")
                            filename = it.get("filename") or f"{mid}"
                            meta_md = it.get("mediaMetadata") or {}
                            base_url = it.get("baseUrl")
                            if not base_url:
                                continue

                            ext = (
                                ext_from_filename(filename)
                                or ext_from_mime(mime)
                                or ("mp4" if is_video_mime(mime) else "jpg")
                            )
                            dl_url = google.build_download_url(base_url, mime)
                            tmp_path, bytes_, ctype = download_to_tmp(dl_url, Path(cfg.tmp_dir))
                            h = sha256_of(tmp_path)
                            if media_exists_by_hash(eng, h):
                                log("sync.item.dup", trace=trace, account_id=aid, media_id=mid)
                                stats["dup"] += 1
                                update_job_stats(eng, job_id, dup=1)
                                tmp_path.unlink(missing_ok=True)
                                continue

                            shot_at = _parse_creation_time(meta_md.get("creationTime"))
                            rel = decide_relpath(shot_at, "gphotos", h, ext)
                            abs_dst = Path(cfg.nas_orig_dir) / rel
                            atomic_move(tmp_path, abs_dst)

                            width = int(meta_md.get("width")) if meta_md.get("width") else None
                            height = int(meta_md.get("height")) if meta_md.get("height") else None
                            is_video = is_video_mime(mime) or ("video" in meta_md)

                            m_id = insert_media(
                                eng,
                                google_media_id=mid,
                                account_id=aid,
                                rel_path=rel,
                                sha256=h,
                                bytes_=bytes_,
                                mime=mime,
                                width=width,
                                height=height,
                                duration_ms=None,
                                shot_at_utc=shot_at,
                                is_video=is_video,
                            )

                            if "photo" in meta_md or meta_md:
                                upsert_exif(eng, m_id, meta_md)

                            if is_video:
                                rel_path = Path(rel)
                                parts = list(rel_path.parts)
                                if parts and parts[0] == "originals":
                                    parts[0] = "playback"
                                play_rel = str(Path(*parts))
                                if not play_rel.endswith(".mp4"):
                                    play_rel = play_rel.rsplit(".", 1)[0] + ".mp4"
                                upsert_media_playback_queue(eng, m_id, play_rel)

                            stats["new"] += 1
                            update_job_stats(eng, job_id, new=1)

                        except Exception as ie:
                            stats["failed"] += 1
                            update_job_stats(eng, job_id, failed=1)
                            log("sync.item.error", trace=trace, account_id=aid, error=str(ie))

                    pages_done += 1
                    if not next_token:
                        break
                    page = next_token

        except google.ReauthRequired as e:
            status = "failed"
            overall_failed += 1
            stats["failed"] += 1
            log("sync.account.reauth_required", trace=trace, account_id=aid, error=str(e))
        except Exception as e:
            status = "failed"
            overall_failed += 1
            stats["failed"] += 1
            log("sync.account.error", trace=trace, account_id=aid, error=str(e))
        finally:
            finalize_job(eng, job_id=job_id, account_id=aid, status=status, stats=stats)

        log("sync.account.end", trace=trace, account_id=aid, status=status, stats=stats)

    log("sync.done", trace=trace, result=("partial" if overall_failed else "success"))
    return 1 if overall_failed else 0
