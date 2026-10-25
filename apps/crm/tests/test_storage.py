import boto3
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse
from moto import mock_aws

from apps.accounts.factories import UserFactory
from apps.crm.models import Company
from apps.projects.factories import ProjectAccessFactory
from apps.tasks.factories import TaskFactory

BUCKET = 'agency-files'


def _storage_post(**overrides):
    data = {
        'storage_backend': 's3',
        's3_endpoint_url': '',
        's3_region': 'eu-central-1',
        's3_bucket': BUCKET,
        's3_access_key': 'AKIATEST',
        's3_secret_key': 'very-secret',
        's3_prefix': '/crm/',
    }
    data.update(overrides)
    return data


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    with mock_aws():
        client = boto3.client('s3', region_name='eu-central-1')
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={'LocationConstraint': 'eu-central-1'},
        )
        yield client


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _keys(s3):
    return [item['Key'] for item in s3.list_objects_v2(Bucket=BUCKET).get('Contents', [])]


@pytest.mark.django_db
class TestStorageSettings:
    def test_admin_connects_a_bucket_after_a_test_write(self, client, admin_user, s3):
        client.force_login(admin_user)
        response = client.post(reverse('settings'), _storage_post())
        assert response.status_code == 302

        company = Company.load()
        assert company.uses_s3
        assert company.s3_prefix == 'crm'
        assert company.s3_secret_key == 'very-secret'
        # The test file was cleaned up.
        assert _keys(s3) == []
        with connection.cursor() as cursor:
            cursor.execute('SELECT s3_secret_key FROM crm_company WHERE id = 1')
            assert cursor.fetchone()[0].startswith('gAAAAA')

        page = client.get(reverse('settings')).content.decode()
        assert 'very-secret' not in page
        assert 'Saved. Leave blank to keep it.' in page

        # A blank secret keeps the saved one.
        response = client.post(reverse('settings'), _storage_post(s3_secret_key=''))
        assert response.status_code == 302
        assert Company.load().s3_secret_key == 'very-secret'

    def test_a_bucket_that_cannot_be_written_saves_nothing(self, client, admin_user, s3):
        client.force_login(admin_user)
        response = client.post(reverse('settings'), _storage_post(s3_bucket='missing-bucket'))
        assert response.status_code == 400
        assert 'Could not write a test file to the bucket' in response.content.decode()
        assert Company.load().storage_backend == Company.STORAGE_DISK
        assert Company.load().s3_bucket == ''

    def test_bucket_name_and_keys_are_required(self, client, admin_user):
        client.force_login(admin_user)
        response = client.post(reverse('settings'), _storage_post(
            s3_bucket='', s3_access_key='', s3_secret_key='',
        ))
        assert response.status_code == 400
        assert response.content.decode().count('Required for a bucket.') == 3

    def test_back_to_disk_needs_no_bucket(self, client, admin_user):
        client.force_login(admin_user)
        response = client.post(reverse('settings'), {'storage_backend': 'disk'})
        assert response.status_code == 302
        assert not Company.load().uses_s3

    def test_member_cannot_change_storage(self, client, user):
        client.force_login(user)
        response = client.post(reverse('settings'), _storage_post())
        assert response.status_code == 403
        assert not Company.load().uses_s3

    def test_disk_warning_in_production_only(self, client, admin_user, settings):
        client.force_login(admin_user)
        warning = 'they are lost on every deploy'
        settings.DEBUG = True
        assert warning not in client.get(reverse('settings')).content.decode()
        settings.DEBUG = False
        settings.STORAGES = {
            **settings.STORAGES,
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        }
        assert warning in client.get(reverse('settings')).content.decode()


@pytest.mark.django_db
class TestAttachmentsInBucket:
    def _connect(self):
        company = Company.load()
        company.storage_backend = Company.STORAGE_S3
        company.s3_region = 'eu-central-1'
        company.s3_bucket = BUCKET
        company.s3_access_key = 'AKIATEST'
        company.s3_secret_key = 'very-secret'
        company.s3_prefix = 'crm'
        company.save()

    def test_upload_goes_to_the_bucket_and_download_is_a_signed_link(self, client, s3):
        self._connect()
        user = UserFactory()
        task = TaskFactory()
        ProjectAccessFactory(project=task.project, user=user)
        client.force_login(user)
        client.post(
            reverse('attachment_upload', args=[task.pk]),
            {'file': SimpleUploadedFile('brief.pdf', b'%PDF-1.4 brief')},
        )
        attachment = task.attachments.get()
        keys = _keys(s3)
        assert keys == [f'crm/{attachment.file.name}']

        response = client.get(reverse('attachment_download', args=[attachment.pk]))
        assert response.status_code == 302
        assert BUCKET in response.url
        assert 'Signature' in response.url or 'X-Amz-Signature' in response.url
        assert 'inline' in response.url

        outsider = UserFactory()
        client.force_login(outsider)
        assert client.get(
            reverse('attachment_download', args=[attachment.pk])
        ).status_code == 403

    def test_a_file_saved_on_disk_before_the_bucket_still_downloads(self, client, s3):
        user = UserFactory()
        task = TaskFactory()
        ProjectAccessFactory(project=task.project, user=user)
        client.force_login(user)
        client.post(
            reverse('attachment_upload', args=[task.pk]),
            {'file': SimpleUploadedFile('old.txt', b'from the disk')},
        )
        attachment = task.attachments.get()
        self._connect()

        response = client.get(reverse('attachment_download', args=[attachment.pk]))
        assert response.status_code == 200
        assert b''.join(response.streaming_content) == b'from the disk'
