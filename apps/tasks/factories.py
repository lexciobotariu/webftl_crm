from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory
from apps.tasks.models import Label, Subtask, Task, TaskActivity, TimeEntry


class LabelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Label

    project = factory.SubFactory(ProjectFactory)
    name = factory.Faker('word')
    color = '#6366f1'


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task

    project = factory.SubFactory(ProjectFactory)
    status = factory.LazyAttribute(lambda o: o.project.statuses.first())
    title = factory.Faker('sentence', nb_words=5)
    description = factory.Faker('paragraph')
    priority = factory.Iterator(['low', 'medium', 'high', 'urgent'])
    order = factory.Sequence(lambda n: n)


class SubtaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subtask

    task = factory.SubFactory(TaskFactory)
    title = factory.Faker('sentence', nb_words=3)
    completed = False
    order = factory.Sequence(lambda n: n)


class TaskActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TaskActivity

    task = factory.SubFactory(TaskFactory)
    user = factory.SubFactory(UserFactory)
    activity_type = 'comment'
    content = factory.Faker('sentence')


class TimeEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TimeEntry

    task = factory.SubFactory(TaskFactory)
    user = factory.SubFactory(UserFactory)
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1))
    ended_at = factory.LazyAttribute(lambda o: o.started_at + timedelta(minutes=30))
    note = ''

    class Params:
        running = factory.Trait(
            started_at=factory.LazyFunction(timezone.now),
            ended_at=None,
        )
