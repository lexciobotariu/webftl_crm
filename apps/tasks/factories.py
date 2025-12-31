import factory
from apps.tasks.models import Task, Subtask, Label, Comment, TaskActivity
from apps.projects.factories import ProjectFactory, StatusFactory
from apps.accounts.factories import UserFactory


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


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    task = factory.SubFactory(TaskFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Faker('paragraph')


class TaskActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TaskActivity

    task = factory.SubFactory(TaskFactory)
    user = factory.SubFactory(UserFactory)
    activity_type = 'comment'
    content = factory.Faker('sentence')
