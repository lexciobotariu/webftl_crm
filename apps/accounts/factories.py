import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'user{n}@example.com')
    name = factory.Faker('name')
    role = 'member'
    github_token = ''
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'testpass123')
        manager = cls._get_manager(model_class)
        return manager.create_user(**kwargs, password=password)


class AdminUserFactory(UserFactory):
    role = 'admin'
    email = factory.Sequence(lambda n: f'admin{n}@example.com')
