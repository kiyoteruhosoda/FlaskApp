from datetime import datetime, timezone
import json
from uuid import uuid4
import requests
from flask import (
	Blueprint, current_app, jsonify, request, session
)
from flask_login import login_required
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.picker_import_item import PickerImportItem
from core.crypto import decrypt

bp = Blueprint('picker_session_api', __name__)

@bp.post("/picker/session")
@login_required
def api_picker_session_create():
	"""Create a Google Photos Picker session."""
	data = request.get_json(silent=True) or {}
	account_id = data.get("account_id")
	title = data.get("title") or "Select from Google Photos"

	if account_id is None:
		account = GoogleAccount.query.filter_by(status="active").first()
		if not account:
			return jsonify({"error": "invalid_account"}), 400
		account_id = account.id
	else:
		if not isinstance(account_id, int):
			return jsonify({"error": "invalid_account"}), 400
		account = GoogleAccount.query.filter_by(id=account_id, status="active").first()
		if not account:
			return jsonify({"error": "not_found"}), 404

	current_app.logger.info(
		json.dumps(
			{
				"ts": datetime.now(timezone.utc).isoformat(),
				"account_id": account_id,
			}
		),
		extra={"event": "picker.create.begin"}
	)

	tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
	refresh_token = tokens.get("refresh_token")
	if not refresh_token:
		return jsonify({"error": "no_refresh_token"}), 401
	token_req = {
		"client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
		"client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
		"grant_type": "refresh_token",
		"refresh_token": refresh_token,
	}
	try:
		token_res = requests.post(
			"https://oauth2.googleapis.com/token", data=token_req, timeout=15
		)
		token_data = token_res.json()
		if "access_token" not in token_data:
			current_app.logger.error(
				json.dumps(
					{
						"ts": datetime.now(timezone.utc).isoformat(),
						"account_id": account_id,
						"response": token_data,
					}
				),
				extra={"event": "picker.create.fail"}
			)
			return (
				jsonify(
					{
						"error": token_data.get("error", "oauth_error"),
						"message": token_data.get("error_description"),
					}
				),
				401,
			)
	except Exception as e:
		current_app.logger.exception(
			json.dumps(
				{
					"ts": datetime.now(timezone.utc).isoformat(),
					"account_id": account_id,
					"message": str(e),
				}
			),
			extra={"event": "picker.create.fail"}
		)
		return jsonify({"error": "oauth_error", "message": str(e)}), 502

	access_token = token_data["access_token"]
	headers = {"Authorization": f"Bearer {access_token}"}
	body = {"title": title}
	try:
		picker_res = requests.post(
			"https://photospicker.googleapis.com/v1/sessions",
			json=body,
			headers=headers,
			timeout=15,
		)
		picker_res.raise_for_status()
		picker_data = picker_res.json()
	except Exception as e:
		current_app.logger.exception(
			json.dumps(
				{
					"ts": datetime.now(timezone.utc).isoformat(),
					"account_id": account_id,
					"message": str(e),
				}
			),
			extra={"event": "picker.create.fail"}
		)
		return jsonify({"error": "picker_error", "message": str(e)}), 502

	ps = PickerSession(account_id=account.id, status="pending")
	db.session.add(ps)
	db.session.commit()
	ps.session_id = picker_data.get("sessionId") or picker_data.get("name")
	ps.picker_uri = picker_data.get("pickerUri")
	expire = picker_data.get("expireTime")
	if expire:
		try:
			ps.expire_time = datetime.fromisoformat(expire.replace("Z", "+00:00"))
		except Exception:
			ps.expire_time = None
	if picker_data.get("pollingConfig"):
		ps.polling_config_json = json.dumps(picker_data.get("pollingConfig"))
	if picker_data.get("pickingConfig"):
		ps.picking_config_json = json.dumps(picker_data.get("pickingConfig"))
	if "mediaItemsSet" in picker_data:
		ps.media_items_set = picker_data.get("mediaItemsSet")
	db.session.commit()
	session["picker_session_id"] = ps.id
	current_app.logger.info(
		json.dumps(
			{
				"ts": datetime.now(timezone.utc).isoformat(),
				"account_id": account_id,
				"picker_session_id": ps.id,
			}
		),
		extra={"event": "picker.create.success"}
	)
	return jsonify(
		{
			"pickerSessionId": ps.id,
			"sessionId": ps.session_id,
			"pickerUri": ps.picker_uri,
			"expireTime": expire,
			"pollingConfig": picker_data.get("pollingConfig"),
			"pickingConfig": picker_data.get("pickingConfig"),
			"mediaItemsSet": picker_data.get("mediaItemsSet"),
		}
	)


@bp.post("/picker/session/<int:picker_session_id>/callback")
def api_picker_session_callback(picker_session_id):
	"""Receive selected media item IDs from Google Photos Picker."""
	ps = PickerSession.query.get(picker_session_id)
	if not ps:
		return jsonify({"error": "not_found"}), 404
	data = request.get_json(silent=True) or {}
	ids = data.get("mediaItemIds") or []
	if isinstance(ids, str):
		ids = [ids]
	saved = 0
	for mid in ids:
		if not isinstance(mid, str):
			continue
		exists = PickerImportItem.query.filter_by(
			picker_session_id=ps.id, media_item_id=mid
		).first()
		if exists:
			continue
		db.session.add(PickerImportItem(picker_session_id=ps.id, media_item_id=mid))
		saved += 1
	ps.selected_count = (ps.selected_count or 0) + saved
	ps.status = "ready"
	if saved > 0:
		ps.media_items_set = True
	db.session.commit()
	return jsonify({"result": "ok", "count": saved})


@bp.get("/picker/session/<int:picker_session_id>")
@login_required
def api_picker_session_status(picker_session_id):
	"""Return status of a picker session."""
	ps = PickerSession.query.get(picker_session_id)
	if not ps:
		return jsonify({"error": "not_found"}), 404
	account = GoogleAccount.query.get(ps.account_id)
	selected = ps.selected_count
	if selected is None and account and account.status == "active" and ps.session_id:
		try:
			tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
			refresh_token = tokens.get("refresh_token")
			if refresh_token:
				token_req = {
					"client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
					"client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
					"grant_type": "refresh_token",
					"refresh_token": refresh_token,
				}
				token_res = requests.post(
					"https://oauth2.googleapis.com/token", data=token_req, timeout=15
				)
				token_data = token_res.json()
				access_token = token_data.get("access_token")
				if access_token:
					res = requests.get(
						f"https://photospicker.googleapis.com/v1/{ps.session_id}",
						headers={"Authorization": f"Bearer {access_token}"},
						timeout=15,
					)
					res.raise_for_status()
					data = res.json()
					selected = (
						data.get("selectedCount")
						or data.get("selectedMediaCount")
						or data.get("selectedMediaItems")
					)
					if data.get("expireTime"):
						try:
							ps.expire_time = datetime.fromisoformat(
								data["expireTime"].replace("Z", "+00:00")
							)
						except Exception:
							pass
					if data.get("pollingConfig"):
						ps.polling_config_json = json.dumps(data.get("pollingConfig"))
					if data.get("pickingConfig"):
						ps.picking_config_json = json.dumps(data.get("pickingConfig"))
					if "mediaItemsSet" in data:
						ps.media_items_set = data.get("mediaItemsSet")
		except Exception:
			selected = None
	ps.selected_count = selected
	ps.last_polled_at = datetime.now(timezone.utc)
	db.session.commit()
	current_app.logger.info(
		json.dumps(
			{
				"ts": datetime.now(timezone.utc).isoformat(),
				"picker_session_id": picker_session_id,
				"status": ps.status,
			}
		),
		extra={"event": "picker.status.get"}
	)
	return jsonify(
		{
			"status": ps.status,
			"selectedCount": ps.selected_count,
			"lastPolledAt": ps.last_polled_at.isoformat().replace("+00:00", "Z"),
			"serverTimeRFC1123": datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT'),
			"sessionId": ps.session_id,
			"pickerUri": ps.picker_uri,
			"expireTime": ps.expire_time.isoformat().replace("+00:00", "Z") if ps.expire_time else None,
			"pollingConfig": json.loads(ps.polling_config_json) if ps.polling_config_json else None,
			"pickingConfig": json.loads(ps.picking_config_json) if ps.picking_config_json else None,
			"mediaItemsSet": ps.media_items_set,
		}
	)


@bp.post("/picker/session/<int:picker_session_id>/import")
@login_required
def api_picker_session_import(picker_session_id):
	"""Enqueue import task for picker session.

	The frontend does not pass ``account_id`` in the request body, so the
	parameter is now optional.  If provided it must match the session's
	``account_id``; otherwise the session's own ``account_id`` is used.
	The picker session status is also updated to ``importing`` so that the
	client can immediately reflect the change in state.
	"""
	data = request.get_json(silent=True) or {}
	account_id = data.get("account_id")
	ps = PickerSession.query.get(picker_session_id)
	if not ps or (account_id and ps.account_id != account_id):
		return jsonify({"error": "not_found"}), 404
	# Use the session's account id when not explicitly supplied
	account_id = account_id or ps.account_id
	if ps.status in ("imported", "canceled", "expired"):
		current_app.logger.info(
			json.dumps(
				{
					"ts": datetime.now(timezone.utc).isoformat(),
					"picker_session_id": picker_session_id,
					"status": ps.status,
				}
			),
			extra={"event": "picker.import.suppress"}
		)
		return jsonify({"error": "already_done"}), 409
	stats = ps.stats()
	if stats.get("celery_task_id"):
		current_app.logger.info(
			json.dumps(
				{
					"ts": datetime.now(timezone.utc).isoformat(),
					"picker_session_id": picker_session_id,
					"status": ps.status,
				}
			),
			extra={"event": "picker.import.suppress"}
		)
		return jsonify({"error": "already_enqueued"}), 409
	task_id = uuid4().hex
	stats["celery_task_id"] = task_id
	ps.set_stats(stats)
	ps.status = "importing"
	db.session.commit()
	current_app.logger.info(
		json.dumps(
			{
				"ts": datetime.now(timezone.utc).isoformat(),
				"picker_session_id": picker_session_id,
				"status": ps.status,
			}
		),
		extra={"event": "picker.import.enqueue"}
	)
	return jsonify({"enqueued": True, "celeryTaskId": task_id}), 202
