"""Where uploaded files live: an S3-compatible bucket set in Settings, or the server disk.

``ConfiguredStorage`` is the project's default storage. It reads the Company row on
every file operation, so a change in Settings reaches every worker at once without a
restart. File operations are rare (an upload, a download), so the one small query
each costs nothing that matters.

Files saved on the disk before the bucket was turned on are still found: reads,
size checks and deletes fall back to the disk when the bucket does not have the name.
"""
import functools
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

# How long a download link to a private bucket works, in seconds.
SIGNED_URL_SECONDS = 300


class StorageCheckError(Exception):
    """The bucket in Settings could not be written, read back, or cleaned up."""


def _disk():
    return FileSystemStorage()


@functools.lru_cache(maxsize=4)
def _bucket(endpoint_url, region, bucket, access_key, secret_key, prefix):
    # Imported here so the disk-only setup never loads boto3.
    from botocore.config import Config
    from storages.backends.s3 import S3Storage

    return S3Storage(
        bucket_name=bucket,
        endpoint_url=endpoint_url or None,
        region_name=region or None,
        access_key=access_key,
        secret_key=secret_key,
        location=prefix.strip('/'),
        # The bucket stays private: every download goes through a short signed link
        # handed out only after the app has checked who is asking.
        default_acl=None,
        querystring_auth=True,
        querystring_expire=SIGNED_URL_SECONDS,
        file_overwrite=False,
        signature_version='s3v4',
        # Settings waits on the test write, so a wrong endpoint must fail fast.
        client_config=Config(
            connect_timeout=5, read_timeout=20, retries={'max_attempts': 2},
            signature_version='s3v4',
        ),
    )


def bucket_for(endpoint_url='', region='', bucket='', access_key='', secret_key='', prefix=''):
    return _bucket(endpoint_url, region, bucket, access_key, secret_key, prefix)


def bucket_from_company(company):
    return bucket_for(
        company.s3_endpoint_url,
        company.s3_region,
        company.s3_bucket,
        company.s3_access_key,
        company.s3_secret_key,
        company.s3_prefix,
    )


def check_bucket(storage):
    """Write a small file, read it back and delete it. Raises StorageCheckError."""
    name = f'webftl-check/{uuid.uuid4().hex}.txt'
    body = b'WebFTL CRM storage check'
    try:
        saved = storage.save(name, ContentFile(body))
        with storage.open(saved, 'rb') as handle:
            read_back = handle.read()
        storage.delete(saved)
    except Exception as exc:  # boto raises many kinds; all mean "not usable"
        raise StorageCheckError(str(exc) or exc.__class__.__name__) from exc
    if read_back != body:
        raise StorageCheckError('The file read back from the bucket was different.')


@deconstructible
class ConfiguredStorage(Storage):
    def _active(self):
        from apps.crm.models import Company

        company = Company.load()
        if company.uses_s3:
            return bucket_from_company(company)
        return _disk()

    def _holding(self, name):
        """The storage that has ``name``: the active one, else the disk."""
        active = self._active()
        if isinstance(active, FileSystemStorage):
            return active
        disk = _disk()
        if not active.exists(name) and disk.exists(name):
            return disk
        return active

    def signed_url(self, name, filename, inline=False):
        """A short-lived link straight to the bucket, or None when files are on disk."""
        storage = self._holding(name)
        if isinstance(storage, FileSystemStorage):
            return None
        disposition = 'inline' if inline else 'attachment'
        safe = filename.replace('"', '')
        return storage.url(name, parameters={
            'ResponseContentDisposition': f'{disposition}; filename="{safe}"',
        })

    def _open(self, name, mode='rb'):
        return self._holding(name).open(name, mode)

    def _save(self, name, content):
        return self._active().save(name, content)

    def get_available_name(self, name, max_length=None):
        return self._active().get_available_name(name, max_length=max_length)

    def delete(self, name):
        self._holding(name).delete(name)

    def exists(self, name):
        return self._holding(name).exists(name)

    def size(self, name):
        return self._holding(name).size(name)

    def url(self, name):
        return self._holding(name).url(name)

    def path(self, name):
        return self._holding(name).path(name)

    def listdir(self, path):
        return self._active().listdir(path)
