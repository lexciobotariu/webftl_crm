import os
import warnings
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv('DEBUG', 'False') == 'True'

_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    if DEBUG:
        SECRET_KEY = 'dev-secret-key'
    else:
        raise ImproperlyConfigured('SECRET_KEY environment variable is required when DEBUG is False')
else:
    SECRET_KEY = _secret_key

_fernet_key = os.getenv('FERNET_KEY')
if not _fernet_key:
    if DEBUG:
        # Ephemeral per-process key — encrypted tokens won't survive restarts.
        from cryptography.fernet import Fernet
        FERNET_KEYS = [Fernet.generate_key().decode()]
    else:
        raise ImproperlyConfigured('FERNET_KEY environment variable is required when DEBUG is False')
else:
    FERNET_KEYS = [_fernet_key]

_allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
if _allowed_hosts:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',') if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
else:
    ALLOWED_HOSTS = []

_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third party
    'allauth',
    'allauth.account',
    'django_htmx',
    # Local apps
    'apps.accounts',
    'apps.clients',
    'apps.projects',
    'apps.tasks',
    'apps.todos',
    'apps.notes',
    'apps.salaries',
    'apps.integrations',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.version',
                'config.context_processors.permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default='postgres://postgres:postgres@localhost:5433/webftl_crm',
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

_staticfiles_backend = (
    'django.contrib.staticfiles.storage.StaticFilesStorage'
    if DEBUG
    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
)
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': _staticfiles_backend,
    },
}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Allauth
ACCOUNT_ADAPTER = 'apps.accounts.adapters.NoSignupAccountAdapter'
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = 'none'

# Email
# The console backend prints mail instead of sending it. That is fine in
# development, but silently swallowing password-reset mail in production is not,
# so outside DEBUG an explicit EMAIL_BACKEND is required and its absence warns.
_email_backend = os.getenv('EMAIL_BACKEND')
if _email_backend:
    EMAIL_BACKEND = _email_backend
elif DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    warnings.warn(
        'EMAIL_BACKEND is not set and DEBUG is False; falling back to the dummy '
        'backend. Password reset and notification mail will be discarded.',
        RuntimeWarning,
        stacklevel=2,
    )
    EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'webmaster@localhost')

# GitHub
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', '')

# Production security headers (enabled when DEBUG is False)
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    # Behind a TLS-terminating proxy, Django sees plain HTTP and SECURE_SSL_REDIRECT
    # would loop forever. Set this only when the proxy is trusted to set the header.
    if os.getenv('USE_X_FORWARDED_PROTO', 'False') == 'True':
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
