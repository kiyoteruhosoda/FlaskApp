"""Tests for webapp.utils.url_helpers module."""

import pytest
from flask import Flask
from unittest.mock import Mock, patch

from webapp.utils.url_helpers import (
    determine_external_scheme,
    _extract_forwarded_proto,
    _extract_x_forwarded_proto,
)


class TestExtractForwardedProto:
    """Tests for _extract_forwarded_proto() helper function."""

    def test_none_header_returns_none(self):
        """None header should return None."""
        assert _extract_forwarded_proto(None) is None

    def test_empty_header_returns_none(self):
        """Empty header should return None."""
        assert _extract_forwarded_proto("") is None

    def test_single_proto_unquoted(self):
        """Parse single proto value without quotes."""
        assert _extract_forwarded_proto("proto=https") == "https"

    def test_single_proto_quoted(self):
        """Parse single proto value with quotes."""
        assert _extract_forwarded_proto('proto="https"') == "https"

    def test_multiple_attributes(self):
        """Parse proto from multiple attributes."""
        assert _extract_forwarded_proto("for=1.2.3.4;proto=https;host=example.com") == "https"

    def test_multiple_forwarded_entries(self):
        """Parse proto from first entry in comma-separated list."""
        assert _extract_forwarded_proto("for=1.2.3.4;proto=https, for=5.6.7.8;proto=http") == "https"

    def test_case_insensitive_proto_key(self):
        """Proto key should be case-insensitive."""
        assert _extract_forwarded_proto("PROTO=https") == "https"
        assert _extract_forwarded_proto("Proto=https") == "https"

    def test_normalizes_to_lowercase(self):
        """Proto value should be normalized to lowercase."""
        assert _extract_forwarded_proto("proto=HTTPS") == "https"
        assert _extract_forwarded_proto("proto=HttPs") == "https"

    def test_whitespace_handling(self):
        """Handle whitespace around values."""
        assert _extract_forwarded_proto("proto=https ") == "https"
        assert _extract_forwarded_proto(' proto="https" ') == "https"

    def test_missing_proto_attribute(self):
        """Return None if proto attribute is not present."""
        assert _extract_forwarded_proto("for=1.2.3.4;host=example.com") is None

    def test_empty_proto_value(self):
        """Return None if proto value is empty."""
        assert _extract_forwarded_proto("proto=") is None
        assert _extract_forwarded_proto('proto=""') is None


class TestExtractXForwardedProto:
    """Tests for _extract_x_forwarded_proto() helper function."""

    def test_none_header_returns_none(self):
        """None header should return None."""
        assert _extract_x_forwarded_proto(None) is None

    def test_empty_header_returns_none(self):
        """Empty header should return None."""
        assert _extract_x_forwarded_proto("") is None

    def test_single_value(self):
        """Parse single proto value."""
        assert _extract_x_forwarded_proto("https") == "https"

    def test_multiple_values_returns_first(self):
        """Return first proto value from comma-separated list."""
        assert _extract_x_forwarded_proto("https, http") == "https"

    def test_normalizes_to_lowercase(self):
        """Proto value should be normalized to lowercase."""
        assert _extract_x_forwarded_proto("HTTPS") == "https"
        assert _extract_x_forwarded_proto("HttPs") == "https"

    def test_whitespace_handling(self):
        """Handle whitespace around values."""
        assert _extract_x_forwarded_proto(" https ") == "https"
        assert _extract_x_forwarded_proto("https , http") == "https"


class TestDetermineExternalScheme:
    """Tests for determine_external_scheme() main function."""

    @pytest.fixture
    def app(self):
        """Create a Flask app for testing."""
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    def test_forwarded_header_takes_precedence(self, app):
        """Forwarded header proto should take precedence over all others."""
        with app.test_request_context(
            "/",
            headers={
                "Forwarded": "proto=https",
                "X-Forwarded-Proto": "http",
            },
            environ_base={"wsgi.url_scheme": "http"},
        ):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = "http"
                assert determine_external_scheme() == "https"

    def test_x_forwarded_proto_second_priority(self, app):
        """X-Forwarded-Proto should be used if Forwarded is not present."""
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-Proto": "https"},
            environ_base={"wsgi.url_scheme": "http"},
        ):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = "http"
                assert determine_external_scheme() == "https"

    def test_preferred_url_scheme_third_priority(self, app):
        """PREFERRED_URL_SCHEME setting should be used if headers are not present."""
        with app.test_request_context("/", environ_base={"wsgi.url_scheme": "http"}):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = "https"
                assert determine_external_scheme() == "https"

    def test_request_scheme_fourth_priority(self, app):
        """Request scheme should be used if headers and settings are not present."""
        with app.test_request_context("/", base_url="https://example.com/"):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = None
                assert determine_external_scheme() == "https"

    def test_fallback_to_https_default(self, app):
        """Should fallback to https if all other methods fail."""
        with app.test_request_context("/"):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = None
                # Mock request to have no scheme
                from flask import request
                mock_req = Mock()
                mock_req.headers.get.return_value = None
                mock_req.scheme = None
                mock_req.environ = {}
                
                assert determine_external_scheme(mock_req) == "https"

    def test_forwarded_header_with_complex_format(self, app):
        """Handle complex Forwarded header format."""
        with app.test_request_context(
            "/",
            headers={
                "Forwarded": 'for=192.0.2.60;proto=https;host=example.com, for=192.0.2.43;proto=http'
            },
        ):
            assert determine_external_scheme() == "https"

    def test_x_forwarded_proto_with_multiple_values(self, app):
        """Handle X-Forwarded-Proto with multiple comma-separated values."""
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-Proto": "https, http, http"},
        ):
            assert determine_external_scheme() == "https"

    def test_preferred_url_scheme_with_uppercase(self, app):
        """PREFERRED_URL_SCHEME should normalize to lowercase."""
        with app.test_request_context("/"):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = "HTTPS"
                assert determine_external_scheme() == "https"

    def test_preferred_url_scheme_with_whitespace(self, app):
        """PREFERRED_URL_SCHEME should strip whitespace."""
        with app.test_request_context("/"):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = "  https  "
                assert determine_external_scheme() == "https"

    def test_request_scheme_attribute(self, app):
        """Use request.scheme if available."""
        with app.test_request_context("/", base_url="http://example.com"):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = None
                assert determine_external_scheme() == "http"

    def test_wsgi_url_scheme_fallback(self, app):
        """Use wsgi.url_scheme if request.scheme is not available."""
        with app.test_request_context("/", environ_base={"wsgi.url_scheme": "http"}):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = None
                # Access the request to get the actual scheme
                from flask import request
                # Override scheme to be None to test wsgi fallback
                with patch.object(request, 'scheme', None):
                    result = determine_external_scheme()
                    assert result == "http"

    def test_explicit_request_parameter(self, app):
        """Should use explicitly provided request parameter."""
        with app.test_request_context("/"):
            mock_req = Mock()
            mock_req.headers.get.return_value = None
            mock_req.scheme = "http"
            mock_req.environ = {"wsgi.url_scheme": "http"}
            
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = None
                assert determine_external_scheme(mock_req) == "http"

    def test_empty_forwarded_proto_fallback(self, app):
        """Empty Forwarded proto should fallback to next priority."""
        with app.test_request_context(
            "/",
            headers={
                "Forwarded": "for=1.2.3.4",
                "X-Forwarded-Proto": "https",
            },
        ):
            assert determine_external_scheme() == "https"

    def test_empty_x_forwarded_proto_fallback(self, app):
        """Empty X-Forwarded-Proto should fallback to next priority."""
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-Proto": ""},
            environ_base={"wsgi.url_scheme": "http"},
        ):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = "https"
                assert determine_external_scheme() == "https"

    def test_http_scheme_not_upgraded(self, app):
        """HTTP scheme should be preserved if explicitly set in headers."""
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-Proto": "http"},
        ):
            assert determine_external_scheme() == "http"

    def test_all_sources_missing(self, app):
        """Should default to https when all sources are missing."""
        with app.test_request_context("/"):
            with patch("webapp.utils.url_helpers.settings") as mock_settings:
                mock_settings.preferred_url_scheme = None
                mock_req = Mock()
                mock_req.headers.get.return_value = None
                mock_req.scheme = None
                mock_req.environ = {}
                
                assert determine_external_scheme(mock_req) == "https"
