"""API リクエスト/レスポンスの構造化ロギングとサーバ時刻付与のフック登録.

``create_app()`` に定義されていたリクエストフック群を集約する。責務は次のとおり:

- リクエスト処理時間の計測（``Server-Timing`` ヘッダ）
- ``/api`` 入出力の構造化ログ（機密マスク・サイズ制御は request_log_payload に委譲）
- 5xx 応答時のサーバエラーログ
- レスポンスへのサーバ時刻付与（``X-Server-Time`` / JSON ``server_time``）

ペイロード整形ロジックには依存するが、整形そのものは持たない（SRP）。after_request
の登録順序は Flask の実行順序（逆順）に影響するため、元の順序を厳守する。
"""

from __future__ import annotations

import json
import time
from uuid import uuid4

from flask import Flask, g, request

from core.time import utc_now_isoformat

from .request_log_payload import (
    format_file_parameters_for_logging,
    format_form_parameters_for_logging,
    mask_sensitive_data,
    prepare_log_payload,
    truncate_long_parameter_values,
)


def register_request_logging(app: Flask) -> None:
    """リクエスト計測・API 入出力ログ・サーバ時刻付与のフックを登録する。"""

    @app.before_request
    def start_timer():
        g.start_time = time.perf_counter()

    @app.before_request
    def log_api_request():
        if request.path.startswith("/api"):
            req_id = str(uuid4())
            g.request_id = req_id
            # Inputログ
            try:
                input_json = request.get_json(silent=True)
            except Exception:
                input_json = None

            log_dict = {
                "method": request.method,
            }
            args_dict = request.args.to_dict()
            if args_dict:
                log_dict["args"] = mask_sensitive_data(args_dict)
            form_dict = format_form_parameters_for_logging(request.form)
            if form_dict:
                log_dict["form"] = mask_sensitive_data(form_dict)
            files_dict = format_file_parameters_for_logging(request.files)
            if files_dict:
                log_dict["files"] = mask_sensitive_data(files_dict)
            if input_json is not None:
                processed_json = (
                    truncate_long_parameter_values(input_json)
                    if request.method.upper() == "POST"
                    else input_json
                )
                log_dict["json"] = mask_sensitive_data(processed_json)
            _, serialized_payload = prepare_log_payload(
                log_dict,
                keys_to_summarize=("json", "form", "args", "files"),
            )
            app.logger.info(
                serialized_payload,
                extra={
                    "event": "api.input",
                    "request_id": req_id,
                    "path": request.path,
                }
            )

    @app.after_request
    def log_api_response(response):
        if request.path.startswith("/api"):
            req_id = getattr(g, "request_id", None)
            resp_json = None
            if response.mimetype == "application/json":
                try:
                    resp_json = response.get_json()
                except Exception as e:
                    print(f"Error parsing JSON response {request.path}:", e)
                    resp_json = None
            masked_json = (
                mask_sensitive_data(resp_json) if resp_json is not None else None
            )
            base_payload = {
                "status": response.status_code,
                "json": masked_json,
            }
            _, log_payload = prepare_log_payload(
                base_payload,
                keys_to_summarize=("json",),
            )
            log_extra = {
                "event": "api.output",
                "request_id": req_id,
                "path": request.path,
            }
            if response.status_code >= 400:
                app.logger.warning(log_payload, extra=log_extra)
            else:
                app.logger.info(log_payload, extra=log_extra)
        return response

    @app.after_request
    def log_server_error(response):
        if response.status_code >= 500 and not getattr(g, "exception_logged", False):
            try:
                input_json = request.get_json(silent=True)
            except Exception:
                input_json = None
            log_dict = {
                "status": response.status_code,
                "method": request.method,
                "user_agent": request.user_agent.string,
            }
            qs = request.query_string.decode()
            if qs:
                log_dict["query_string"] = qs
            form_dict = request.form.to_dict()
            if form_dict:
                log_dict["form"] = mask_sensitive_data(form_dict)
            if input_json is not None:
                log_dict["json"] = mask_sensitive_data(input_json)
            app.logger.error(
                json.dumps(log_dict, ensure_ascii=False),
                extra={
                    "event": "api.server_error",
                    "path": request.url,
                    "request_id": getattr(g, "request_id", None),
                },
            )
        return response

    @app.after_request
    def add_server_timing(response):
        start = getattr(g, "start_time", None)
        if start is not None:
            duration = (time.perf_counter() - start) * 1000
            response.headers["Server-Timing"] = f"app;dur={duration:.2f}"
        return response

    @app.after_request
    def inject_server_time(response):
        server_time_value = utc_now_isoformat()
        response.headers["X-Server-Time"] = server_time_value

        if response.mimetype == "application/json":
            try:
                payload = response.get_json()
            except Exception:
                payload = None

            if isinstance(payload, dict):
                payload["server_time"] = server_time_value
                response.set_data(app.json.dumps(payload))
                response.mimetype = "application/json"

        return response
