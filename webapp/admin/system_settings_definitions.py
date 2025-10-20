"""Definitions and metadata for editable system settings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from flask_babel import gettext as _


SettingFieldType = Literal["string", "integer", "float", "boolean", "list"]

_ALLOWED_FIELD_TYPES: tuple[SettingFieldType, ...] = (
    "string",
    "integer",
    "float",
    "boolean",
    "list",
)


@dataclass(frozen=True)
class SettingFieldDefinition:
    """Metadata describing a configurable JSON property."""

    key: str
    label: str
    data_type: SettingFieldType
    required: bool
    description: str
    allow_empty: bool = False
    allow_null: bool = False
    multiline: bool = False
    choices: Sequence[tuple[str, str]] | None = None
    default_hint: str | None = None

    def __post_init__(self) -> None:
        if self.data_type not in _ALLOWED_FIELD_TYPES:
            raise ValueError(f"Unsupported data type '{self.data_type}' for {self.key}")
        if not isinstance(self.required, bool):
            raise TypeError("'required' must be a boolean value")

    def choice_labels(self) -> Sequence[tuple[str, str]]:
        return self.choices or ()


BOOLEAN_CHOICES: tuple[tuple[str, str], ...] = (
    ("true", _(u"True")),
    ("false", _(u"False")),
)


APPLICATION_SETTING_DEFINITIONS: Mapping[str, SettingFieldDefinition] = {
    "SECRET_KEY": SettingFieldDefinition(
        key="SECRET_KEY",
        label=_(u"Flask secret key"),
        data_type="string",
        required=True,
        description=_(u"Secret used to sign session cookies and CSRF tokens."),
        allow_empty=False,
    ),
    "JWT_SECRET_KEY": SettingFieldDefinition(
        key="JWT_SECRET_KEY",
        label=_(u"JWT secret key"),
        data_type="string",
        required=True,
        description=_(u"HS256 secret used for application issued JWT tokens."),
        allow_empty=False,
    ),
    "ACCESS_TOKEN_ISSUER": SettingFieldDefinition(
        key="ACCESS_TOKEN_ISSUER",
        label=_(u"Access token issuer"),
        data_type="string",
        required=True,
        description=_(u"Issuer (`iss`) claim embedded in generated access tokens."),
    ),
    "ACCESS_TOKEN_AUDIENCE": SettingFieldDefinition(
        key="ACCESS_TOKEN_AUDIENCE",
        label=_(u"Access token audience"),
        data_type="string",
        required=True,
        description=_(u"Audience (`aud`) claim enforced for access tokens."),
    ),
    "SESSION_COOKIE_SECURE": SettingFieldDefinition(
        key="SESSION_COOKIE_SECURE",
        label=_(u"Secure session cookie"),
        data_type="boolean",
        required=True,
        description=_(u"Set secure attribute on Flask session cookies."),
        choices=BOOLEAN_CHOICES,
    ),
    "SESSION_COOKIE_HTTPONLY": SettingFieldDefinition(
        key="SESSION_COOKIE_HTTPONLY",
        label=_(u"HTTPOnly session cookie"),
        data_type="boolean",
        required=True,
        description=_(u"Disallow JavaScript access to Flask session cookies."),
        choices=BOOLEAN_CHOICES,
    ),
    "SESSION_COOKIE_SAMESITE": SettingFieldDefinition(
        key="SESSION_COOKIE_SAMESITE",
        label=_(u"Session cookie SameSite"),
        data_type="string",
        required=True,
        description=_(u"SameSite policy for Flask session cookies."),
        choices=(
            ("Lax", "Lax"),
            ("Strict", "Strict"),
            ("None", "None"),
        ),
    ),
    "PERMANENT_SESSION_LIFETIME": SettingFieldDefinition(
        key="PERMANENT_SESSION_LIFETIME",
        label=_(u"Session lifetime (seconds)"),
        data_type="integer",
        required=True,
        description=_(u"Lifetime for permanent sessions expressed in seconds."),
    ),
    "PREFERRED_URL_SCHEME": SettingFieldDefinition(
        key="PREFERRED_URL_SCHEME",
        label=_(u"Preferred URL scheme"),
        data_type="string",
        required=True,
        description=_(u"Scheme used when Flask builds external URLs."),
        choices=(
            ("http", "http"),
            ("https", "https"),
        ),
    ),
    "CERTS_API_TIMEOUT": SettingFieldDefinition(
        key="CERTS_API_TIMEOUT",
        label=_(u"Certificates API timeout"),
        data_type="float",
        required=True,
        description=_(u"Timeout in seconds for certificate service requests."),
    ),
    "LANGUAGES": SettingFieldDefinition(
        key="LANGUAGES",
        label=_(u"Supported languages"),
        data_type="list",
        required=True,
        description=_(u"Ordered list of supported locale codes."),
        multiline=True,
    ),
    "BABEL_DEFAULT_LOCALE": SettingFieldDefinition(
        key="BABEL_DEFAULT_LOCALE",
        label=_(u"Default locale"),
        data_type="string",
        required=True,
        description=_(u"Primary locale used for translations."),
    ),
    "BABEL_DEFAULT_TIMEZONE": SettingFieldDefinition(
        key="BABEL_DEFAULT_TIMEZONE",
        label=_(u"Default timezone"),
        data_type="string",
        required=True,
        description=_(u"Timezone used for localized datetime rendering."),
    ),
    "GOOGLE_CLIENT_ID": SettingFieldDefinition(
        key="GOOGLE_CLIENT_ID",
        label=_(u"Google OAuth client ID"),
        data_type="string",
        required=False,
        description=_(u"Client identifier for Google sign-in."),
        allow_empty=True,
    ),
    "GOOGLE_CLIENT_SECRET": SettingFieldDefinition(
        key="GOOGLE_CLIENT_SECRET",
        label=_(u"Google OAuth client secret"),
        data_type="string",
        required=False,
        description=_(u"Client secret for Google sign-in."),
        allow_empty=True,
    ),
    "OAUTH_TOKEN_KEY": SettingFieldDefinition(
        key="OAUTH_TOKEN_KEY",
        label=_(u"OAuth token key"),
        data_type="string",
        required=False,
        description=_(u"PEM encoded key used for OAuth token exchange."),
        allow_empty=True,
        allow_null=True,
    ),
    "OAUTH_TOKEN_KEY_FILE": SettingFieldDefinition(
        key="OAUTH_TOKEN_KEY_FILE",
        label=_(u"OAuth token key file"),
        data_type="string",
        required=False,
        description=_(u"Path to a PEM file used for OAuth token exchange."),
        allow_empty=True,
        allow_null=True,
    ),
    "FPV_DL_SIGN_KEY": SettingFieldDefinition(
        key="FPV_DL_SIGN_KEY",
        label=_(u"Download signing key"),
        data_type="string",
        required=False,
        description=_(u"Signing key used for download URLs."),
        allow_empty=True,
    ),
    "FPV_URL_TTL_THUMB": SettingFieldDefinition(
        key="FPV_URL_TTL_THUMB",
        label=_(u"Thumbnail URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for thumbnail download URLs."),
    ),
    "FPV_URL_TTL_PLAYBACK": SettingFieldDefinition(
        key="FPV_URL_TTL_PLAYBACK",
        label=_(u"Playback URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for playback download URLs."),
    ),
    "FPV_URL_TTL_ORIGINAL": SettingFieldDefinition(
        key="FPV_URL_TTL_ORIGINAL",
        label=_(u"Original URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for original asset download URLs."),
    ),
    "UPLOAD_TMP_DIR": SettingFieldDefinition(
        key="UPLOAD_TMP_DIR",
        label=_(u"Upload temporary directory"),
        data_type="string",
        required=True,
        description=_(u"Temporary storage path for uploads."),
    ),
    "UPLOAD_DESTINATION_DIR": SettingFieldDefinition(
        key="UPLOAD_DESTINATION_DIR",
        label=_(u"Upload destination directory"),
        data_type="string",
        required=True,
        description=_(u"Permanent storage path for uploaded files."),
    ),
    "UPLOAD_MAX_SIZE": SettingFieldDefinition(
        key="UPLOAD_MAX_SIZE",
        label=_(u"Upload max size (bytes)"),
        data_type="integer",
        required=True,
        description=_(u"Maximum upload size in bytes."),
    ),
    "WIKI_UPLOAD_DIR": SettingFieldDefinition(
        key="WIKI_UPLOAD_DIR",
        label=_(u"Wiki upload directory"),
        data_type="string",
        required=True,
        description=_(u"Storage path for wiki attachments."),
    ),
    "FPV_NAS_THUMBS_DIR": SettingFieldDefinition(
        key="FPV_NAS_THUMBS_DIR",
        label=_(u"NAS thumbnails directory"),
        data_type="string",
        required=False,
        description=_(u"NAS path for cached thumbnails."),
        allow_empty=True,
    ),
    "FPV_NAS_PLAY_DIR": SettingFieldDefinition(
        key="FPV_NAS_PLAY_DIR",
        label=_(u"NAS playback directory"),
        data_type="string",
        required=False,
        description=_(u"NAS path for playback assets."),
        allow_empty=True,
    ),
    "FPV_ACCEL_THUMBS_LOCATION": SettingFieldDefinition(
        key="FPV_ACCEL_THUMBS_LOCATION",
        label=_(u"Accel thumbnail location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for thumbnail assets."),
        allow_empty=True,
    ),
    "FPV_ACCEL_PLAYBACK_LOCATION": SettingFieldDefinition(
        key="FPV_ACCEL_PLAYBACK_LOCATION",
        label=_(u"Accel playback location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for playback assets."),
        allow_empty=True,
    ),
    "FPV_ACCEL_ORIGINALS_LOCATION": SettingFieldDefinition(
        key="FPV_ACCEL_ORIGINALS_LOCATION",
        label=_(u"Accel originals location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for original assets."),
        allow_empty=True,
    ),
    "FPV_ACCEL_REDIRECT_ENABLED": SettingFieldDefinition(
        key="FPV_ACCEL_REDIRECT_ENABLED",
        label=_(u"Enable acceleration redirects"),
        data_type="boolean",
        required=True,
        description=_(u"Enable redirect responses when acceleration paths exist."),
        choices=BOOLEAN_CHOICES,
    ),
    "LOCAL_IMPORT_DIR": SettingFieldDefinition(
        key="LOCAL_IMPORT_DIR",
        label=_(u"Local import directory"),
        data_type="string",
        required=True,
        description=_(u"Local path watched for media imports."),
    ),
    "FPV_NAS_ORIGINALS_DIR": SettingFieldDefinition(
        key="FPV_NAS_ORIGINALS_DIR",
        label=_(u"NAS originals directory"),
        data_type="string",
        required=True,
        description=_(u"NAS path containing original media assets."),
    ),
    "CELERY_BROKER_URL": SettingFieldDefinition(
        key="CELERY_BROKER_URL",
        label=_(u"Celery broker URL"),
        data_type="string",
        required=True,
        description=_(u"Connection URL for the Celery broker."),
    ),
    "CELERY_RESULT_BACKEND": SettingFieldDefinition(
        key="CELERY_RESULT_BACKEND",
        label=_(u"Celery result backend"),
        data_type="string",
        required=True,
        description=_(u"Connection URL for the Celery result backend."),
    ),
    "SERVICE_ACCOUNT_SIGNING_AUDIENCE": SettingFieldDefinition(
        key="SERVICE_ACCOUNT_SIGNING_AUDIENCE",
        label=_(u"Service account signing audience"),
        data_type="string",
        required=False,
        description=_(u"Audience claim issued for service account tokens."),
        allow_empty=True,
    ),
    "TRANSCODE_CRF": SettingFieldDefinition(
        key="TRANSCODE_CRF",
        label=_(u"Transcode CRF"),
        data_type="integer",
        required=True,
        description=_(u"Constant Rate Factor used for video transcoding."),
    ),
}


CORS_SETTING_DEFINITIONS: Mapping[str, SettingFieldDefinition] = {
    "allowedOrigins": SettingFieldDefinition(
        key="allowedOrigins",
        label=_(u"Allowed origins"),
        data_type="list",
        required=False,
        description=_(u"List of origins allowed by the CORS policy."),
        multiline=True,
        allow_empty=True,
    )
}


__all__ = [
    "SettingFieldDefinition",
    "SettingFieldType",
    "APPLICATION_SETTING_DEFINITIONS",
    "CORS_SETTING_DEFINITIONS",
]
