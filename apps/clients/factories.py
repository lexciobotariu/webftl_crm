import factory

from apps.clients.models import Client


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    name = factory.Faker('company')
    email = factory.Faker('company_email')
    phone = factory.Faker('phone_number')
    address = factory.Faker('address')
    notes = factory.Faker('paragraph')
