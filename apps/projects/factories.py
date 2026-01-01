import factory
from apps.projects.models import Project, Status, ProjectMember
from apps.clients.factories import ClientFactory
from apps.accounts.factories import UserFactory


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    client = factory.SubFactory(ClientFactory)
    name = factory.Faker('catch_phrase')
    description = factory.Faker('paragraph')
    github_repo_url = ''
    github_sync_enabled = False


class StatusFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Status

    project = factory.SubFactory(ProjectFactory)
    name = factory.Faker('word')
    order = factory.Sequence(lambda n: n)


class ProjectMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectMember

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    role = 'editor'
