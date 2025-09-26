# -*- coding: utf-8 -*-
"""
共通ページング機能

無限スクロール対応のカーソルベースページングとオフセットベース
ページングの両方をサポートする共通ロジック。
"""

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from flask import request, current_app
from sqlalchemy import asc, desc
from sqlalchemy.orm import Query


class PaginationParams:
    """ページングパラメータを管理するクラス"""
    
    def __init__(self,
                 page: Optional[int] = None,
                 page_size: Optional[int] = None,
                 cursor: Optional[str] = None,
                 order: str = "desc",
                 use_cursor: Optional[bool] = None):
        self.page = page or 1
        if page_size is None:
            page_size = 200
        self.page_size = min(max(page_size, 1), 500)
        self.cursor = cursor
        self.order = order.lower() if order else "desc"

        if use_cursor is None:
            use_cursor = bool(cursor)
        self.use_cursor = use_cursor
    
    @classmethod
    def from_request(cls, default_page_size: int = 200) -> 'PaginationParams':
        """リクエストパラメータからPaginationParamsを生成"""
        page_str = request.args.get("page")
        try:
            page = int(page_str) if page_str is not None else 1
        except (ValueError, TypeError):
            page = 1

        try:
            page_size = int(request.args.get("pageSize", default_page_size))
        except (ValueError, TypeError):
            page_size = default_page_size

        cursor = request.args.get("cursor")
        order = request.args.get("order", "desc")

        use_cursor = cursor is not None or page_str is None

        return cls(
            page=page,
            page_size=page_size,
            cursor=cursor,
            order=order,
            use_cursor=use_cursor,
        )


class CursorInfo:
    """カーソル情報を管理するクラス"""
    
    def __init__(self, 
                 id_value: Optional[int] = None,
                 shot_at: Optional[datetime] = None,
                 created_at: Optional[datetime] = None,
                 **kwargs):
        self.id_value = id_value
        self.shot_at = shot_at
        self.created_at = created_at
        self.extra = kwargs
    
    @classmethod
    def from_cursor_string(cls, cursor_str: str) -> Optional['CursorInfo']:
        """Base64エンコードされたカーソル文字列から復元"""
        if not cursor_str:
            return None
            
        try:
            # Base64デコード
            cursor_bytes = base64.urlsafe_b64decode(cursor_str + '==')  # パディング追加
            cursor_data = json.loads(cursor_bytes.decode('utf-8'))
            
            # datetimeの復元
            shot_at = None
            created_at = None
            
            if cursor_data.get('shot_at'):
                shot_at = datetime.fromisoformat(cursor_data['shot_at'].replace('Z', '+00:00'))
            if cursor_data.get('created_at'):
                created_at = datetime.fromisoformat(cursor_data['created_at'].replace('Z', '+00:00'))
                
            return cls(
                id_value=cursor_data.get('id'),
                shot_at=shot_at,
                created_at=created_at,
                **{k: v for k, v in cursor_data.items() 
                   if k not in ['id', 'shot_at', 'created_at']}
            )
        except Exception as e:
            # アプリケーションコンテキスト外ではログ出力をスキップ
            try:
                current_app.logger.warning(f"Invalid cursor format: {e}")
            except RuntimeError:
                # テスト環境など、アプリケーションコンテキスト外
                pass
            return None
    
    def to_cursor_string(self) -> str:
        """Base64エンコードされたカーソル文字列に変換"""
        cursor_data = {'id': self.id_value}
        
        if self.shot_at:
            cursor_data['shot_at'] = self.shot_at.isoformat().replace('+00:00', 'Z')
        if self.created_at:
            cursor_data['created_at'] = self.created_at.isoformat().replace('+00:00', 'Z')
            
        # 追加データ
        cursor_data.update(self.extra)
        
        cursor_json = json.dumps(cursor_data, separators=(',', ':'))
        cursor_bytes = cursor_json.encode('utf-8')
        return base64.urlsafe_b64encode(cursor_bytes).decode('utf-8').rstrip('=')


class PaginatedResult:
    """ページング結果を管理するクラス"""
    
    def __init__(self,
                 items: List[Any],
                 total_count: Optional[int] = None,
                 next_cursor: Optional[str] = None,
                 prev_cursor: Optional[str] = None,
                 has_next: bool = False,
                 has_prev: bool = False,
                 current_page: Optional[int] = None,
                 total_pages: Optional[int] = None):
        self.items = items
        self.total_count = total_count
        self.next_cursor = next_cursor
        self.prev_cursor = prev_cursor
        self.has_next = has_next
        self.has_prev = has_prev
        self.current_page = current_page
        self.total_pages = total_pages
    
    def to_dict(self, include_server_time: bool = True) -> Dict[str, Any]:
        """辞書形式に変換"""
        result = {
            "items": self.items,
            "hasNext": self.has_next,
            "hasPrev": self.has_prev,
        }
        
        # カーソルベースの情報
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        if self.prev_cursor is not None:
            result["prevCursor"] = self.prev_cursor
            
        # ページベースの情報
        if self.current_page is not None:
            result["currentPage"] = self.current_page
        if self.total_pages is not None:
            result["totalPages"] = self.total_pages
        if self.total_count is not None:
            result["totalCount"] = self.total_count
            
        # サーバー時刻
        if include_server_time:
            server_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            result["serverTime"] = server_time
            
        return result


class Paginator:
    """共通ページング処理クラス"""
    
    @staticmethod
    def paginate_query(query: Query,
                      params: PaginationParams,
                      id_column=None,
                      shot_at_column=None,
                      created_at_column=None,
                      count_total: bool = False) -> PaginatedResult:
        """
        SQLAlchemyクエリをページング処理
        
        Args:
            query: ページングするクエリ
            params: ページングパラメータ
            id_column: IDカラム（カーソルベース用）
            shot_at_column: shot_atカラム（ソート用）
            created_at_column: created_atカラム（ソート用）
            count_total: 総件数をカウントするかどうか
            
        Returns:
            PaginatedResult: ページング結果
        """
        
        # 総件数の取得（必要な場合のみ）
        total_count = None
        if count_total and not params.use_cursor:
            total_count = query.count()
        
        # カーソルベースページング
        if params.use_cursor:
            return Paginator._paginate_with_cursor(
                query, params, id_column, shot_at_column, created_at_column
            )
        
        # オフセットベースページング
        return Paginator._paginate_with_offset(
            query, params, total_count, id_column, shot_at_column, created_at_column
        )
    
    @staticmethod
    def _paginate_with_cursor(query: Query,
                            params: PaginationParams,
                            id_column=None,
                            shot_at_column=None,
                            created_at_column=None) -> PaginatedResult:
        """カーソルベースページング"""
        
        # カーソル情報の解析
        cursor_info = CursorInfo.from_cursor_string(params.cursor) if params.cursor else None
        
        # ソート条件の適用
        if shot_at_column is not None:
            # shot_at + id のソート
            if params.order == "asc":
                query = query.order_by(
                    shot_at_column.is_(None),
                    asc(shot_at_column),
                    asc(id_column) if id_column else None
                )
            else:
                query = query.order_by(
                    shot_at_column.is_(None),
                    desc(shot_at_column),
                    desc(id_column) if id_column else None
                )
                
            # カーソル条件の適用
            if cursor_info:
                if cursor_info.shot_at is not None:
                    if params.order == "asc":
                        query = query.filter(
                            (shot_at_column > cursor_info.shot_at) |
                            ((shot_at_column == cursor_info.shot_at) &
                             (id_column > cursor_info.id_value)) if id_column else True
                        )
                    else:
                        query = query.filter(
                            (shot_at_column < cursor_info.shot_at) |
                            ((shot_at_column == cursor_info.shot_at) &
                             (id_column < cursor_info.id_value)) if id_column else True
                        )
                elif id_column is not None and cursor_info.id_value is not None:
                    # shot_at が欠落しているカーソルでは ID でフォールバックする
                    if params.order == "asc":
                        query = query.filter(id_column > cursor_info.id_value)
                    else:
                        query = query.filter(id_column < cursor_info.id_value)
                    
        elif created_at_column is not None:
            # created_at + id のソート
            if params.order == "asc":
                query = query.order_by(asc(created_at_column), asc(id_column) if id_column else None)
            else:
                query = query.order_by(desc(created_at_column), desc(id_column) if id_column else None)
                
            # カーソル条件の適用
            if cursor_info and cursor_info.created_at is not None:
                if params.order == "asc":
                    query = query.filter(
                        (created_at_column > cursor_info.created_at) |
                        ((created_at_column == cursor_info.created_at) & 
                         (id_column > cursor_info.id_value)) if id_column else True
                    )
                else:
                    query = query.filter(
                        (created_at_column < cursor_info.created_at) |
                        ((created_at_column == cursor_info.created_at) & 
                         (id_column < cursor_info.id_value)) if id_column else True
                    )
                    
        elif id_column is not None:
            # IDのみのソート
            if params.order == "asc":
                query = query.order_by(asc(id_column))
            else:
                query = query.order_by(desc(id_column))
                
            # カーソル条件の適用
            if cursor_info and cursor_info.id_value is not None:
                if params.order == "asc":
                    query = query.filter(id_column > cursor_info.id_value)
                else:
                    query = query.filter(id_column < cursor_info.id_value)
        
        # データの取得（1件多く取得して次ページの有無を判定）
        items = query.limit(params.page_size + 1).all()
        
        # 次ページの有無判定
        has_next = len(items) > params.page_size
        if has_next:
            items = items[:-1]  # 余分な1件を削除
        
        # 次のカーソル生成
        next_cursor = None
        if has_next and items:
            last_item = items[-1]
            if hasattr(last_item, 'shot_at') and shot_at_column is not None:
                next_cursor = CursorInfo(
                    id_value=getattr(last_item, id_column.name) if id_column else None,
                    shot_at=last_item.shot_at
                ).to_cursor_string()
            elif hasattr(last_item, 'created_at') and created_at_column is not None:
                next_cursor = CursorInfo(
                    id_value=getattr(last_item, id_column.name) if id_column else None,
                    created_at=last_item.created_at
                ).to_cursor_string()
            elif id_column is not None:
                next_cursor = CursorInfo(
                    id_value=getattr(last_item, id_column.name)
                ).to_cursor_string()
        
        return PaginatedResult(
            items=items,
            next_cursor=next_cursor,
            has_next=has_next,
            has_prev=bool(cursor_info)  # カーソルがあれば前ページありと判定
        )
    
    @staticmethod
    def _paginate_with_offset(query: Query,
                            params: PaginationParams,
                            total_count: Optional[int],
                            id_column=None,
                            shot_at_column=None,
                            created_at_column=None) -> PaginatedResult:
        """オフセットベースページング"""
        
        # ソート条件の適用
        if shot_at_column is not None:
            if params.order == "asc":
                query = query.order_by(
                    shot_at_column.is_(None),
                    asc(shot_at_column),
                    asc(id_column) if id_column else None
                )
            else:
                query = query.order_by(
                    shot_at_column.is_(None),
                    desc(shot_at_column),
                    desc(id_column) if id_column else None
                )
        elif created_at_column is not None:
            if params.order == "asc":
                query = query.order_by(asc(created_at_column), asc(id_column) if id_column else None)
            else:
                query = query.order_by(desc(created_at_column), desc(id_column) if id_column else None)
        elif id_column is not None:
            if params.order == "asc":
                query = query.order_by(asc(id_column))
            else:
                query = query.order_by(desc(id_column))
        
        # オフセットとリミットの適用
        offset = (params.page - 1) * params.page_size
        items = query.offset(offset).limit(params.page_size).all()
        
        # ページ情報の計算
        total_pages = None
        if total_count is not None:
            total_pages = (total_count + params.page_size - 1) // params.page_size
        
        has_next = bool(total_pages and params.page < total_pages)
        has_prev = params.page > 1
        
        return PaginatedResult(
            items=items,
            total_count=total_count,
            has_next=has_next,
            has_prev=has_prev,
            current_page=params.page,
            total_pages=total_pages
        )


# 便利関数
def paginate_and_respond(query: Query,
                        params: Optional[PaginationParams] = None,
                        serializer_func=None,
                        id_column=None,
                        shot_at_column=None,
                        created_at_column=None,
                        count_total: bool = False,
                        default_page_size: int = 200) -> Dict[str, Any]:
    """
    クエリをページングして辞書形式で返す便利関数
    
    Args:
        query: ページングするクエリ
        params: ページングパラメータ（Noneの場合はリクエストから取得）
        serializer_func: アイテムのシリアライズ関数
        id_column: IDカラム
        shot_at_column: shot_atカラム
        created_at_column: created_atカラム
        count_total: 総件数をカウントするか
        default_page_size: デフォルトページサイズ
        
    Returns:
        Dict: ページング結果の辞書
    """
    if params is None:
        params = PaginationParams.from_request(default_page_size)
    
    result = Paginator.paginate_query(
        query=query,
        params=params,
        id_column=id_column,
        shot_at_column=shot_at_column,
        created_at_column=created_at_column,
        count_total=count_total
    )
    
    # アイテムのシリアライズ
    if serializer_func:
        result.items = [serializer_func(item) for item in result.items]
    
    return result.to_dict()
