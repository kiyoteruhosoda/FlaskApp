"""Definitions and metadata for editable system settings."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
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
    editable: bool = True

    def __post_init__(self) -> None:
        if self.data_type not in _ALLOWED_FIELD_TYPES:
            raise ValueError(f"Unsupported data type '{self.data_type}' for {self.key}")
        if not isinstance(self.required, bool):
            raise TypeError("'required' must be a boolean value")
        if not isinstance(self.editable, bool):
            raise TypeError("'editable' must be a boolean value")

    def choice_labels(self) -> Sequence[tuple[str, str]]:
        return self.choices or ()


@dataclass(frozen=True)
class SettingDefinitionSection:
    """Logical grouping used to organise settings in the admin UI."""

    identifier: str
    label: str
    description: str | None
    fields: Sequence[SettingFieldDefinition]


BOOLEAN_CHOICES: tuple[tuple[str, str], ...] = (
    ("true", _(u"True")),
    ("false", _(u"False")),
)

_SECURITY_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="SECRET_KEY",
        label=_(u"Flask secret key"),
        data_type="string",
        required=True,
        description=_(u"Secret used to sign session cookies and CSRF tokens."),
        allow_empty=False,
    ),
    SettingFieldDefinition(
        key="JWT_SECRET_KEY",
        label=_(u"JWT secret key"),
        data_type="string",
        required=True,
        description=_(u"HS256 secret used for application issued JWT tokens."),
        allow_empty=False,
    ),
    SettingFieldDefinition(
        key="ACCESS_TOKEN_ISSUER",
        label=_(u"Access token issuer"),
        data_type="string",
        required=True,
        description=_(u"Issuer (`iss`) claim embedded in generated access tokens."),
    ),
    SettingFieldDefinition(
        key="ACCESS_TOKEN_AUDIENCE",
        label=_(u"Access token audience"),
        data_type="string",
        required=True,
        description=_(u"Audience (`aud`) claim enforced for access tokens."),
    ),
)

_SESSION_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="SESSION_COOKIE_SECURE",
        label=_(u"Secure session cookie"),
        data_type="boolean",
        required=True,
        description=_(u"Set secure attribute on Flask session cookies."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="SESSION_COOKIE_HTTPONLY",
        label=_(u"HTTPOnly session cookie"),
        data_type="boolean",
        required=True,
        description=_(u"Disallow JavaScript access to Flask session cookies."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
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
    SettingFieldDefinition(
        key="PERMANENT_SESSION_LIFETIME",
        label=_(u"Session lifetime (seconds)"),
        data_type="integer",
        required=True,
        description=_(u"Lifetime for permanent sessions expressed in seconds."),
    ),
    SettingFieldDefinition(
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
    SettingFieldDefinition(
        key="CERTS_API_TIMEOUT",
        label=_(u"Certificates API timeout"),
        data_type="float",
        required=True,
        description=_(u"Timeout in seconds for certificate service requests."),
    ),
)

_I18N_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="LANGUAGES",
        label=_(u"Supported languages"),
        data_type="list",
        required=True,
        description=_(u"Ordered list of supported locale codes."),
        multiline=True,
    ),
    SettingFieldDefinition(
        key="BABEL_DEFAULT_LOCALE",
        label=_(u"Default locale"),
        data_type="string",
        required=True,
        description=_(u"Primary locale used for translations."),
    ),
    SettingFieldDefinition(
        key="BABEL_DEFAULT_TIMEZONE",
        label=_(u"Default timezone"),
        data_type="string",
        required=True,
        description=_(u"Timezone used for localized datetime rendering."),
    ),
)

_OAUTH_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="GOOGLE_CLIENT_ID",
        label=_(u"Google OAuth client ID"),
        data_type="string",
        required=False,
        description=_(u"Client identifier for Google sign-in."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="GOOGLE_CLIENT_SECRET",
        label=_(u"Google OAuth client secret"),
        data_type="string",
        required=False,
        description=_(u"Client secret for Google sign-in."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="OAUTH_TOKEN_KEY",
        label=_(u"OAuth token key"),
        data_type="string",
        required=False,
        description=_(u"PEM encoded key used for OAuth token exchange."),
        allow_empty=True,
        allow_null=True,
    ),
    SettingFieldDefinition(
        key="OAUTH_TOKEN_KEY_FILE",
        label=_(u"OAuth token key file"),
        data_type="string",
        required=False,
        description=_(u"Path to a PEM file used for OAuth token exchange."),
        allow_empty=True,
        allow_null=True,
    ),
)

_DOWNLOAD_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="FPV_DL_SIGN_KEY",
        label=_(u"Download signing key"),
        data_type="string",
        required=False,
        description=_(u"Signing key used for download URLs."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="FPV_URL_TTL_THUMB",
        label=_(u"Thumbnail URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for thumbnail download URLs."),
    ),
    SettingFieldDefinition(
        key="FPV_URL_TTL_PLAYBACK",
        label=_(u"Playback URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for playback download URLs."),
    ),
    SettingFieldDefinition(
        key="FPV_URL_TTL_ORIGINAL",
        label=_(u"Original URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for original asset download URLs."),
    ),
)

_STORAGE_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="FPV_TMP_DIR",
        label=_(u"Temporary working directory"),
        data_type="string",
        required=True,
        description=_(u"Directory used for intermediate processing files."),
    ),
    SettingFieldDefinition(
        key="UPLOAD_TMP_DIR",
        label=_(u"Upload temporary directory"),
        data_type="string",
        required=True,
        description=_(u"Temporary storage path for uploads."),
    ),
    SettingFieldDefinition(
        key="UPLOAD_DESTINATION_DIR",
        label=_(u"Upload destination directory"),
        data_type="string",
        required=True,
        description=_(u"Permanent storage path for uploaded files."),
    ),
    SettingFieldDefinition(
        key="UPLOAD_MAX_SIZE",
        label=_(u"Upload max size (bytes)"),
        data_type="integer",
        required=True,
        description=_(u"Maximum upload size in bytes."),
    ),
    SettingFieldDefinition(
        key="WIKI_UPLOAD_DIR",
        label=_(u"Wiki upload directory"),
        data_type="string",
        required=True,
        description=_(u"Storage path for wiki attachments."),
    ),
    SettingFieldDefinition(
        key="FPV_NAS_THUMBS_DIR",
        label=_(u"NAS thumbnails directory"),
        data_type="string",
        required=False,
        description=_(u"NAS path for cached thumbnails."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="FPV_NAS_PLAY_DIR",
        label=_(u"NAS playback directory"),
        data_type="string",
        required=False,
        description=_(u"NAS path for playback assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="FPV_ACCEL_THUMBS_LOCATION",
        label=_(u"Accel thumbnail location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for thumbnail assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="FPV_ACCEL_PLAYBACK_LOCATION",
        label=_(u"Accel playback location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for playback assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="FPV_ACCEL_ORIGINALS_LOCATION",
        label=_(u"Accel originals location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for original assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="FPV_ACCEL_REDIRECT_ENABLED",
        label=_(u"Enable acceleration redirects"),
        data_type="boolean",
        required=True,
        description=_(u"Enable redirect responses when acceleration paths exist."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="LOCAL_IMPORT_DIR",
        label=_(u"Local import directory"),
        data_type="string",
        required=True,
        description=_(u"Local path watched for media imports."),
    ),
    SettingFieldDefinition(
        key="BACKUP_DIR",
        label=_(u"Backup directory"),
        data_type="string",
        required=True,
        description=_(u"Destination directory for scheduled backups."),
    ),
    SettingFieldDefinition(
        key="FPV_NAS_ORIGINALS_DIR",
        label=_(u"NAS originals directory"),
        data_type="string",
        required=True,
        description=_(u"NAS path containing original media assets."),
    ),
)

_CELERY_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="CELERY_BROKER_URL",
        label=_(u"Celery broker URL"),
        data_type="string",
        required=True,
        description=_(u"Connection URL for the Celery broker."),
    ),
    SettingFieldDefinition(
        key="CELERY_RESULT_BACKEND",
        label=_(u"Celery result backend"),
        data_type="string",
        required=True,
        description=_(u"Connection URL for the Celery result backend."),
    ),
)

_SERVICE_ACCOUNT_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="SERVICE_ACCOUNT_SIGNING_AUDIENCE",
        label=_(u"Service account signing audience"),
        data_type="string",
        required=False,
        description=_(u"Audience claim issued for service account tokens."),
        allow_empty=True,
    ),
)

_MEDIA_PROCESSING_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="TRANSCODE_CRF",
        label=_(u"Transcode CRF"),
        data_type="integer",
        required=True,
        description=_(u"Constant Rate Factor used for video transcoding."),
    ),
)

APPLICATION_SETTING_SECTIONS: tuple[SettingDefinitionSection, ...] = (
    SettingDefinitionSection(
        identifier="security",
        label=_(u"Security & Signing"),
        description=_(u"Secrets, issuers, and token signing settings."),
        fields=_SECURITY_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="sessions",
        label=_(u"Session Management"),
        description=_(u"Cookie policies and request lifetime controls."),
        fields=_SESSION_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="internationalization",
        label=_(u"Internationalization"),
        description=_(u"Supported locales and localisation defaults."),
        fields=_I18N_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="identity",
        label=_(u"Identity Providers"),
        description=_(u"OAuth and external authentication credentials."),
        fields=_OAUTH_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="downloads",
        label=_(u"Download Links"),
        description=_(u"Temporary URL signing keys and lifetimes."),
        fields=_DOWNLOAD_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="storage",
        label=_(u"Storage & Paths"),
        description=_(u"Directories for uploads, caches, and backups."),
        fields=_STORAGE_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="celery",
        label=_(u"Background Tasks"),
        description=_(u"Celery broker and result backend configuration."),
        fields=_CELERY_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="service-accounts",
        label=_(u"Service Accounts"),
        description=_(u"Settings related to service account tokens."),
        fields=_SERVICE_ACCOUNT_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="media-processing",
        label=_(u"Media Processing"),
        description=_(u"Transcoding pipeline defaults."),
        fields=_MEDIA_PROCESSING_DEFINITIONS,
    ),
)


def _build_section_metadata(
    sections: Sequence[SettingDefinitionSection],
) -> tuple[Mapping[str, SettingFieldDefinition], Mapping[str, str]]:
    definitions: dict[str, SettingFieldDefinition] = {}
    section_index: dict[str, str] = {}
    for section in sections:
        for definition in section.fields:
            if definition.key in definitions:
                raise ValueError(
                    f"Duplicate system setting key registered: {definition.key}"
                )
            definitions[definition.key] = definition
            section_index[definition.key] = section.identifier
    return MappingProxyType(definitions), MappingProxyType(section_index)


APPLICATION_SETTING_DEFINITIONS, APPLICATION_SETTING_SECTION_INDEX = _build_section_metadata(
    APPLICATION_SETTING_SECTIONS
)


CORS_SETTING_DEFINITIONS: Mapping[str, SettingFieldDefinition] = MappingProxyType(
    {
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
)


__all__ = [
    "SettingFieldDefinition",
    "SettingFieldType",
    "SettingDefinitionSection",
    "APPLICATION_SETTING_SECTIONS",
    "APPLICATION_SETTING_SECTION_INDEX",
    "APPLICATION_SETTING_DEFINITIONS",
    "CORS_SETTING_DEFINITIONS",
]
