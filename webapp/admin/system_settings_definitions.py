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
    SettingFieldDefinition(
        key="SERVICE_ACCOUNT_SIGNING_AUDIENCE",
        label=_(u"Service account signing audience"),
        data_type="string",
        required=False,
        description=_(u"Audience claim issued for service account tokens."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="ENCRYPTION_KEY",
        label=_(u"Token encryption key"),
        data_type="string",
        required=False,
        description=_(
            u"32-byte base64 key used to encrypt Google account refresh tokens. "
            "Changing this value prevents previously stored tokens from being decrypted."
        ),
        allow_empty=True,
        allow_null=True,
        default_hint=_(
            u"Default: base64:ZGVmYXVsdC1nb29nbGUtZW5jcnlwdGlvbi1rZXktISE= "
            "(preconfigured for Google integration)."
        ),
    ),
    SettingFieldDefinition(
        key="WEBAUTHN_RP_ID",
        label=_(u"WebAuthn relying party ID"),
        data_type="string",
        required=True,
        description=_(
            u"Domain name asserted during WebAuthn registration and authentication. "
            "Must match the cookie / TLS host." 
        ),
    ),
    SettingFieldDefinition(
        key="WEBAUTHN_ORIGIN",
        label=_(u"WebAuthn origin"),
        data_type="string",
        required=True,
        description=_(
            u"Origin expected by the browser when verifying WebAuthn challenges "
            "(scheme + host + optional port)."
        ),
        default_hint=_(u"Defaults to http://localhost:5000 in development."),
    ),
    SettingFieldDefinition(
        key="WEBAUTHN_RP_NAME",
        label=_(u"WebAuthn relying party name"),
        data_type="string",
        required=True,
        description=_(
            u"Human readable label presented to users during WebAuthn prompts."
        ),
        default_hint=_(u'Appears to users as "Nolumia" unless overridden.'),
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
        description=_(
            u"Timeout in seconds for certificate service requests. Set to 0 to wait indefinitely."
        ),
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
)

_DOWNLOAD_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="MEDIA_DOWNLOAD_SIGNING_KEY",
        label=_(u"Download signing key"),
        data_type="string",
        required=False,
        description=_(u"Signing key used for download URLs."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MEDIA_THUMBNAIL_URL_TTL_SECONDS",
        label=_(u"Thumbnail URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for thumbnail download URLs."),
    ),
    SettingFieldDefinition(
        key="MEDIA_PLAYBACK_URL_TTL_SECONDS",
        label=_(u"Playback URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for playback download URLs."),
    ),
    SettingFieldDefinition(
        key="MEDIA_ORIGINAL_URL_TTL_SECONDS",
        label=_(u"Original URL TTL"),
        data_type="integer",
        required=True,
        description=_(u"Validity in seconds for original asset download URLs."),
    ),
)

_STORAGE_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="MEDIA_TEMP_DIRECTORY",
        label=_(u"Temporary working directory"),
        data_type="string",
        required=True,
        description=_(u"Directory used for intermediate processing files."),
    ),
    SettingFieldDefinition(
        key="MEDIA_UPLOAD_TEMP_DIRECTORY",
        label=_(u"Upload temporary directory"),
        data_type="string",
        required=True,
        description=_(u"Temporary storage path for uploads."),
    ),
    SettingFieldDefinition(
        key="MEDIA_UPLOAD_DESTINATION_DIRECTORY",
        label=_(u"Upload destination directory"),
        data_type="string",
        required=True,
        description=_(u"Permanent storage path for uploaded files."),
    ),
    SettingFieldDefinition(
        key="MEDIA_UPLOAD_MAX_SIZE_BYTES",
        label=_(u"Upload max size (bytes)"),
        data_type="integer",
        required=True,
        description=_(u"Maximum upload size in bytes."),
    ),
    SettingFieldDefinition(
        key="MEDIA_LOCAL_IMPORT_DIRECTORY",
        label=_(u"Local import directory"),
        data_type="string",
        required=True,
        description=_(u"Local path watched for media imports."),
    ),
    SettingFieldDefinition(
        key="MEDIA_THUMBNAILS_DIRECTORY",
        label=_(u"NAS thumbnails directory"),
        data_type="string",
        required=False,
        description=_(u"NAS path for cached thumbnails."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MEDIA_PLAYBACK_DIRECTORY",
        label=_(u"NAS playback directory"),
        data_type="string",
        required=False,
        description=_(u"NAS path for playback assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MEDIA_ORIGINALS_DIRECTORY",
        label=_(u"NAS originals directory"),
        data_type="string",
        required=True,
        description=_(u"NAS path containing original media assets."),
    ),
    SettingFieldDefinition(
        key="MEDIA_ACCEL_REDIRECT_ENABLED",
        label=_(u"Enable acceleration redirects"),
        data_type="boolean",
        required=True,
        description=_(u"Enable redirect responses when acceleration paths exist."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="MEDIA_ACCEL_THUMBNAILS_LOCATION",
        label=_(u"Accel thumbnail location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for thumbnail assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MEDIA_ACCEL_PLAYBACK_LOCATION",
        label=_(u"Accel playback location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for playback assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MEDIA_ACCEL_ORIGINALS_LOCATION",
        label=_(u"Accel originals location"),
        data_type="string",
        required=False,
        description=_(u"Acceleration mapping for original assets."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="SYSTEM_BACKUP_DIRECTORY",
        label=_(u"System backup directory"),
        data_type="string",
        required=True,
        description=_(
            u"Destination directory for database, media, and configuration backups."
        ),
    ),
    SettingFieldDefinition(
        key="WIKI_UPLOAD_DIRECTORY",
        label=_(u"Wiki upload directory"),
        data_type="string",
        required=True,
        description=_(u"Storage path for wiki attachments."),
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
        allow_null=True,
    ),
)

_PLATFORM_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="SQLALCHEMY_DATABASE_URI",
        label=_(u"SQLAlchemy database URI"),
        data_type="string",
        required=True,
        description=_(u"Effective database connection string loaded by the application."),
        editable=False,
    ),
    SettingFieldDefinition(
        key="SQLALCHEMY_ENGINE_OPTIONS",
        label=_(u"SQLAlchemy engine options"),
        data_type="string",
        required=True,
        description=_(u"Connection pool parameters applied to the SQLAlchemy engine."),
        editable=False,
        multiline=True,
    ),
    SettingFieldDefinition(
        key="SQLALCHEMY_TRACK_MODIFICATIONS",
        label=_(u"SQLAlchemy track modifications flag"),
        data_type="boolean",
        required=True,
        description=_(u"Whether SQLAlchemy event system tracking is enabled."),
        editable=False,
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="BABEL_TRANSLATION_DIRECTORIES",
        label=_(u"Babel translation directories"),
        data_type="string",
        required=True,
        description=_(u"Filesystem path searched for translation catalogues."),
        editable=False,
        multiline=True,
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

_MAIL_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="MAIL_ENABLED",
        label=_(u"Enable mail functionality"),
        data_type="boolean",
        required=True,
        description=_(u"Enable or disable email sending functionality."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="MAIL_PROVIDER",
        label=_(u"Mail provider"),
        data_type="string",
        required=True,
        description=_(u"Email provider type. Currently only 'smtp' is supported."),
        default_hint=_(u"Only 'smtp' is supported in production."),
        editable=False,
    ),
    SettingFieldDefinition(
        key="MAIL_SERVER",
        label=_(u"SMTP server"),
        data_type="string",
        required=False,
        description=_(u"SMTP server hostname or IP address."),
        allow_empty=True,
        default_hint=_(u"Example: smtp.gmail.com"),
    ),
    SettingFieldDefinition(
        key="MAIL_PORT",
        label=_(u"SMTP port"),
        data_type="integer",
        required=True,
        description=_(u"SMTP server port number."),
        default_hint=_(u"Common ports: 587 (TLS), 465 (SSL), 25 (plain)"),
    ),
    SettingFieldDefinition(
        key="MAIL_USE_TLS",
        label=_(u"Use TLS"),
        data_type="boolean",
        required=True,
        description=_(u"Enable STARTTLS for SMTP connection."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="MAIL_USE_SSL",
        label=_(u"Use SSL"),
        data_type="boolean",
        required=True,
        description=_(u"Use SSL/TLS wrapper for SMTP connection."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="MAIL_USERNAME",
        label=_(u"SMTP username"),
        data_type="string",
        required=False,
        description=_(u"Username for SMTP authentication."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MAIL_PASSWORD",
        label=_(u"SMTP password"),
        data_type="string",
        required=False,
        description=_(u"Password for SMTP authentication."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="MAIL_DEFAULT_SENDER",
        label=_(u"Default sender"),
        data_type="string",
        required=False,
        description=_(u"Default email address used as sender. Falls back to MAIL_USERNAME if empty."),
        allow_empty=True,
    ),
)


_CDN_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="CDN_ENABLED",
        label=_(u"Enable CDN"),
        data_type="boolean",
        required=True,
        description=_(u"Enable or disable CDN functionality for media delivery."),
        choices=BOOLEAN_CHOICES,
        default_hint=_(u"Disable to use direct storage URLs"),
    ),
    SettingFieldDefinition(
        key="CDN_PROVIDER",
        label=_(u"CDN provider"),
        data_type="string",
        required=True,
        description=_(u"CDN service provider to use."),
        choices=(
            ("none", _(u"No CDN (Direct storage)")),
            ("azure", _(u"Azure CDN")),
            ("cloudflare", _(u"CloudFlare CDN")),
            ("generic", _(u"Generic CDN")),
        ),
        default_hint=_(u"Select 'none' to disable CDN"),
    ),
    SettingFieldDefinition(
        key="CDN_AZURE_ACCOUNT_NAME",
        label=_(u"Azure CDN account name"),
        data_type="string", 
        required=False,
        description=_(u"Azure CDN account name (required when provider is 'azure')."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_AZURE_ACCESS_KEY",
        label=_(u"Azure CDN access key"),
        data_type="string",
        required=False,
        description=_(u"Azure CDN access key for API operations."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_AZURE_PROFILE",
        label=_(u"Azure CDN profile"),
        data_type="string",
        required=False,
        description=_(u"Azure CDN profile name."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_AZURE_ENDPOINT",
        label=_(u"Azure CDN endpoint"),
        data_type="string",
        required=False,
        description=_(u"Azure CDN endpoint name."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_CLOUDFLARE_API_TOKEN",
        label=_(u"CloudFlare API token"),
        data_type="string",
        required=False,
        description=_(u"CloudFlare API token (required when provider is 'cloudflare')."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_CLOUDFLARE_ZONE_ID",
        label=_(u"CloudFlare zone ID"),
        data_type="string",
        required=False,
        description=_(u"CloudFlare DNS zone identifier."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_CLOUDFLARE_ORIGIN_HOSTNAME",
        label=_(u"CloudFlare origin hostname"),
        data_type="string",
        required=False,
        description=_(u"Origin server hostname for CloudFlare CDN."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_GENERIC_ENDPOINT",
        label=_(u"Generic CDN endpoint"),
        data_type="string",
        required=False,
        description=_(u"API endpoint URL for generic CDN provider."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_GENERIC_API_TOKEN", 
        label=_(u"Generic CDN API token"),
        data_type="string",
        required=False,
        description=_(u"API token for generic CDN provider."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="CDN_CACHE_TTL",
        label=_(u"Cache TTL (seconds)"),
        data_type="integer",
        required=True,
        description=_(u"Default cache time-to-live in seconds for CDN content."),
        default_hint=_(u"Common values: 3600 (1h), 86400 (24h)"),
    ),
    SettingFieldDefinition(
        key="CDN_ENABLE_COMPRESSION",
        label=_(u"Enable compression"),
        data_type="boolean",
        required=True,
        description=_(u"Enable gzip/brotli compression at CDN edge servers."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="CDN_SECURE_URLS_ENABLED",
        label=_(u"Enable secure URLs"),
        data_type="boolean",
        required=True,
        description=_(u"Enable time-limited and IP-restricted secure URLs."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="CDN_ACCESS_KEY",
        label=_(u"CDN access key"),
        data_type="string",
        required=False,
        description=_(u"Secret key for signing secure CDN URLs (required when secure URLs are enabled)."),
        allow_empty=True,
    ),
)


_BLOB_DEFINITIONS: tuple[SettingFieldDefinition, ...] = (
    SettingFieldDefinition(
        key="BLOB_ENABLED",
        label=_(u"Enable Azure Blob Storage"),
        data_type="boolean",
        required=True,
        description=_(u"Enable or disable Azure Blob Storage functionality for media storage."),
        choices=BOOLEAN_CHOICES,
        default_hint=_(u"Disable to use local storage only"),
    ),
    SettingFieldDefinition(
        key="BLOB_PROVIDER",
        label=_(u"Blob storage provider"),
        data_type="string",
        required=True,
        description=_(u"Blob storage service provider to use."),
        choices=(
            ("none", _(u"No Blob storage (Local only)")),
            ("azure", _(u"Azure Blob Storage")),
            ("local", _(u"Local file system")),
        ),
        default_hint=_(u"Select 'none' to disable Blob storage"),
    ),
    SettingFieldDefinition(
        key="BLOB_CONNECTION_STRING",
        label=_(u"Azure Blob connection string"),
        data_type="string",
        required=False,
        description=_(u"Complete Azure Blob Storage connection string (preferred method)."),
        allow_empty=True,
        default_hint=_(u"Format: DefaultEndpointsProtocol=https;AccountName=...;AccountKey=..."),
    ),
    SettingFieldDefinition(
        key="BLOB_ACCOUNT_NAME",
        label=_(u"Azure Blob account name"),
        data_type="string", 
        required=False,
        description=_(u"Azure Storage account name (alternative to connection string)."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="BLOB_ACCESS_KEY",
        label=_(u"Azure Blob access key"),
        data_type="string",
        required=False,
        description=_(u"Azure Storage account access key (alternative to connection string)."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="BLOB_CONTAINER_NAME",
        label=_(u"Blob container name"),
        data_type="string",
        required=True,
        description=_(u"Name of the Azure Blob container for storing media files."),
        default_hint=_(u"Default: photonest"),
    ),
    SettingFieldDefinition(
        key="BLOB_SAS_TOKEN",
        label=_(u"Azure Blob SAS token"),
        data_type="string",
        required=False,
        description=_(u"Shared Access Signature token for Azure Blob access (optional)."),
        allow_empty=True,
    ),
    SettingFieldDefinition(
        key="BLOB_ENDPOINT_SUFFIX",
        label=_(u"Azure endpoint suffix"),
        data_type="string",
        required=True,
        description=_(u"Azure Storage endpoint suffix (usually core.windows.net)."),
        default_hint=_(u"Default: core.windows.net"),
    ),
    SettingFieldDefinition(
        key="BLOB_SECURE_TRANSFER",
        label=_(u"Require secure transfer"),
        data_type="boolean",
        required=True,
        description=_(u"Require HTTPS for all Azure Blob Storage operations."),
        choices=BOOLEAN_CHOICES,
        default_hint=_(u"Recommended: True"),
    ),
    SettingFieldDefinition(
        key="BLOB_CREATE_CONTAINER_IF_NOT_EXISTS",
        label=_(u"Auto-create container"),
        data_type="boolean",
        required=True,
        description=_(u"Automatically create the container if it doesn't exist."),
        choices=BOOLEAN_CHOICES,
    ),
    SettingFieldDefinition(
        key="BLOB_PUBLIC_ACCESS_LEVEL",
        label=_(u"Public access level"),
        data_type="string",
        required=True,
        description=_(u"Container public access level for new containers."),
        choices=(
            ("none", _(u"Private (No public access)")),
            ("blob", _(u"Blob (Public blob access only)")),
            ("container", _(u"Container (Full public access)")),
        ),
        default_hint=_(u"Recommended: Private for security"),
    ),
)

APPLICATION_SETTING_SECTIONS: tuple[SettingDefinitionSection, ...] = (
    SettingDefinitionSection(
        identifier="security",
        label=_(u"Security & Signing"),
        description=_(u"Secrets, encryption keys, issuers, and token signing settings."),
        fields=_SECURITY_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="sessions",
        label=_(u"Session Management"),
        description=_(u"Cookie policies and request lifetime controls."),
        fields=_SESSION_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="platform",
        label=_(u"Application Platform"),
        description=_(u"Runtime environment values exposed for reference."),
        fields=_PLATFORM_DEFINITIONS,
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
        identifier="media-processing",
        label=_(u"Media Processing"),
        description=_(u"Transcoding pipeline defaults."),
        fields=_MEDIA_PROCESSING_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="mail",
        label=_(u"Mail Configuration"),
        description=_(u"Email server settings and mail functionality."),
        fields=_MAIL_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="cdn",
        label=_(u"CDN Configuration"),
        description=_(u"Content Delivery Network settings for faster global media delivery."),
        fields=_CDN_DEFINITIONS,
    ),
    SettingDefinitionSection(
        identifier="blob",
        label=_(u"Blob Storage Configuration"),
        description=_(u"Azure Blob Storage settings for scalable media file storage."),
        fields=_BLOB_DEFINITIONS,
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


READONLY_APPLICATION_SETTING_KEYS: frozenset[str] = frozenset(
    key
    for key, definition in APPLICATION_SETTING_DEFINITIONS.items()
    if not definition.editable
)


CORS_SETTING_DEFINITIONS: Mapping[str, SettingFieldDefinition] = MappingProxyType(
    {
        "CORS_ALLOWED_ORIGINS": SettingFieldDefinition(
            key="CORS_ALLOWED_ORIGINS",
            label=_(u"Effective allowed origins"),
            data_type="list",
            required=False,
            description=_(u"Read-only list of origins currently applied to the Flask app."),
            multiline=True,
            allow_empty=True,
            editable=False,
            default_hint=_(u"Updated automatically after saving allowedOrigins."),
        ),
        "allowedOrigins": SettingFieldDefinition(
            key="allowedOrigins",
            label=_(u"Allowed origins"),
            data_type="list",
            required=False,
            description=_(u"List of origins allowed by the CORS policy."),
            multiline=True,
            allow_empty=True,
        ),
    }
)


__all__ = [
    "SettingFieldDefinition",
    "SettingFieldType",
    "SettingDefinitionSection",
    "APPLICATION_SETTING_SECTIONS",
    "APPLICATION_SETTING_SECTION_INDEX",
    "APPLICATION_SETTING_DEFINITIONS",
    "READONLY_APPLICATION_SETTING_KEYS",
    "CORS_SETTING_DEFINITIONS",
]
