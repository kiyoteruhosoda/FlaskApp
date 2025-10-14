from features.photonest.domain.local_import.import_result import ImportTaskResult


def test_import_task_result_add_error_marks_failed():
    result = ImportTaskResult()

    result.add_error("失敗しました")

    assert result.ok is False
    assert result.errors == ["失敗しました"]


def test_collect_failure_reasons_deduplicates_entries():
    result = ImportTaskResult()
    result.add_error("A")
    result.add_error("A", mark_failed=False)
    result.append_detail({"status": "failed", "reason": "B", "file": "x.jpg"})
    result.append_detail({"status": "failed", "reason": "B", "file": "x.jpg"})

    reasons = result.collect_failure_reasons()

    assert reasons == ["A", "x.jpg: B"]


def test_to_dict_includes_optional_metadata():
    result = ImportTaskResult()
    result.increment_processed()
    result.increment_success()
    result.set_session_id("S1")
    result.set_celery_task_id("C1")
    result.set_thumbnail_snapshot({"status": "completed"})
    result.set_duplicates(duplicates=2, manually_skipped=1)
    result.set_failure_reasons(["reason1"])
    result.set_metadata("extra", "value")

    payload = result.to_dict()

    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert payload["success"] == 1
    assert payload["session_id"] == "S1"
    assert payload["celery_task_id"] == "C1"
    assert payload["thumbnail_snapshot"] == {"status": "completed"}
    assert payload["duplicates"] == 2
    assert payload["manually_skipped"] == 1
    assert payload["failure_reasons"] == ["reason1"]
    assert payload["extra"] == "value"
