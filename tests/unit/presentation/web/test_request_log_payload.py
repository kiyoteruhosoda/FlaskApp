"""`presentation/web/request_log_payload.py` の単体テスト。

ログ整形ロジックは機密マスクとサイズ制御という監査・セキュリティ上重要な
振る舞いを担うため、純粋関数として境界条件まで網羅的に検証する。
"""

from werkzeug.datastructures import FileStorage, MultiDict

from presentation.web.request_log_payload import (
    MAX_LOG_PAYLOAD_BYTES,
    MAX_POST_PARAM_STRING_LENGTH,
    format_file_parameters_for_logging,
    format_form_parameters_for_logging,
    is_sensitive_key,
    mask_sensitive_data,
    prepare_log_payload,
    serialize_for_logging,
    summarize_file_storage,
    summarize_for_logging,
    truncate_long_parameter_values,
)


class TestIsSensitiveKey:
    def test_detects_keyword_case_insensitively(self):
        assert is_sensitive_key("Password") is True
        assert is_sensitive_key("ACCESS_TOKEN") is True
        assert is_sensitive_key("user_api_key") is True

    def test_non_sensitive_key(self):
        assert is_sensitive_key("username") is False

    def test_non_string_key(self):
        assert is_sensitive_key(123) is False
        assert is_sensitive_key(None) is False


class TestMaskSensitiveData:
    def test_masks_top_level_secret(self):
        assert mask_sensitive_data({"password": "p@ss"}) == {"password": "***"}

    def test_masks_nested_structures(self):
        data = {
            "user": {"name": "alice", "secret": "s"},
            "items": [{"token": "t"}, {"id": 1}],
        }
        assert mask_sensitive_data(data) == {
            "user": {"name": "alice", "secret": "***"},
            "items": [{"token": "***"}, {"id": 1}],
        }

    def test_leaves_strings_and_scalars_untouched(self):
        assert mask_sensitive_data("plain") == "plain"
        assert mask_sensitive_data(42) == 42

    def test_does_not_recurse_into_strings(self):
        # 文字列は Sequence だが要素分解せずそのまま返す。
        assert mask_sensitive_data(["password", "ok"]) == ["password", "ok"]


class TestSummarizeForLogging:
    def test_scalars_pass_through(self):
        assert summarize_for_logging(None) is None
        assert summarize_for_logging(True) is True
        assert summarize_for_logging(3.5) == 3.5

    def test_long_string_is_truncated_with_length_marker(self):
        value = "x" * 200
        result = summarize_for_logging(value, _max_string_length=10)
        assert result == f"{'x' * 10}… (200 chars)"

    def test_bytes_are_summarized(self):
        assert summarize_for_logging(b"abc") == "<binary 3 bytes>"

    def test_depth_limit_summarizes_nested_dict(self):
        data = {"a": {"b": {"c": 1}}}
        result = summarize_for_logging(data, _max_depth=1)
        assert result["a"]["type"] == "dict"
        assert result["a"]["length"] == 1

    def test_list_is_sampled(self):
        data = list(range(5))
        result = summarize_for_logging(data, _max_list_items=2)
        assert result["length"] == 5
        assert result["sample"] == [0, 1]
        assert result["..."] == "3 more items"

    def test_dict_items_capped(self):
        data = {f"k{i}": i for i in range(12)}
        result = summarize_for_logging(data, _max_dict_items=10)
        assert result["..."] == "2 more keys"


class TestSerializeForLogging:
    def test_returns_text_and_utf8_byte_length(self):
        text, size = serialize_for_logging({"k": "あ"})
        assert "あ" in text
        assert size == len(text.encode("utf-8"))


class TestPrepareLogPayload:
    def test_small_payload_returned_unchanged(self):
        payload = {"status": 200, "json": {"ok": True}}
        working, text = prepare_log_payload(payload, keys_to_summarize=("json",))
        assert working == payload
        assert text == serialize_for_logging(payload)[0]

    def test_oversized_payload_is_summarized(self):
        big = {"items": [{"v": "x" * 100} for _ in range(2000)]}
        payload = {"status": 200, "json": big}
        working, text = prepare_log_payload(
            payload, keys_to_summarize=("json",), max_bytes=2000
        )
        assert len(text.encode("utf-8")) <= 2000
        assert working["_truncation"]["limitBytes"] == 2000
        assert working["_truncation"]["json"]["summary"] is True

    def test_payload_omitted_when_summary_still_too_large(self):
        payload = {"status": 500, "json": {"v": "x" * 100}}
        working, text = prepare_log_payload(
            payload, keys_to_summarize=("json",), max_bytes=10
        )
        # 上限が極端に小さい場合は本文を省略する。
        assert working["_truncation"]["omitted"] is True
        assert "message" in working

    def test_default_limit_constant(self):
        assert MAX_LOG_PAYLOAD_BYTES == 60_000


class TestTruncateLongParameterValues:
    def test_long_string_truncated(self):
        value = "y" * (MAX_POST_PARAM_STRING_LENGTH + 5)
        result = truncate_long_parameter_values(value)
        assert result.endswith(f"({len(value)} chars)")
        assert result.startswith("y" * MAX_POST_PARAM_STRING_LENGTH)

    def test_short_string_untouched(self):
        assert truncate_long_parameter_values("short") == "short"

    def test_structure_is_preserved(self):
        data = {"a": ["x", {"b": "y"}]}
        assert truncate_long_parameter_values(data) == data

    def test_bytes_summarized(self):
        assert truncate_long_parameter_values(b"abcd") == "<binary 4 bytes>"


class TestFormatFormParametersForLogging:
    def test_empty_form_returns_empty_dict(self):
        assert format_form_parameters_for_logging(MultiDict()) == {}

    def test_single_value_is_scalar(self):
        form = MultiDict([("name", "alice")])
        assert format_form_parameters_for_logging(form) == {"name": "alice"}

    def test_multiple_values_kept_as_list(self):
        form = MultiDict([("tag", "a"), ("tag", "b")])
        assert format_form_parameters_for_logging(form) == {"tag": ["a", "b"]}

    def test_long_values_are_truncated(self):
        long = "z" * (MAX_POST_PARAM_STRING_LENGTH + 1)
        form = MultiDict([("bio", long)])
        result = format_form_parameters_for_logging(form)
        assert result["bio"].endswith("chars)")


class TestFileParameterLogging:
    def test_summarize_file_storage_keeps_only_metadata(self):
        storage = FileStorage(
            filename="photo.jpg", content_type="image/jpeg"
        )
        summary = summarize_file_storage(storage)
        assert summary["omitted"] is True
        assert summary["filename"] == "photo.jpg"
        assert summary["contentType"] == "image/jpeg"

    def test_empty_files_returns_empty_dict(self):
        assert format_file_parameters_for_logging(MultiDict()) == {}

    def test_single_file_is_scalar(self):
        files = MultiDict([("avatar", FileStorage(filename="a.png"))])
        result = format_file_parameters_for_logging(files)
        assert result["avatar"]["filename"] == "a.png"
        assert result["avatar"]["omitted"] is True

    def test_multiple_files_kept_as_list(self):
        files = MultiDict(
            [
                ("docs", FileStorage(filename="1.pdf")),
                ("docs", FileStorage(filename="2.pdf")),
            ]
        )
        result = format_file_parameters_for_logging(files)
        assert [item["filename"] for item in result["docs"]] == ["1.pdf", "2.pdf"]
