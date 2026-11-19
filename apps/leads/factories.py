import factory

from .models import Lead, LeadSource, LeadStatus

# The statuses and sources leads migration 0002 seeds.
STATUSES = (
    ('New', LeadStatus.OPEN, 'blue'),
    ('Contacted', LeadStatus.OPEN, 'violet'),
    ('Proposal sent', LeadStatus.OPEN, 'amber'),
    ('Won', LeadStatus.WON, 'green'),
    ('Lost', LeadStatus.LOST, 'red'),
)


def ensure_statuses():
    """The seeded statuses, back after a TransactionTestCase flushed them. Returns them by name."""
    if not LeadStatus.objects.exists():
        for position, (name, kind, color) in enumerate(STATUSES):
            LeadStatus.objects.create(name=name, kind=kind, color=color, position=position)
    return {status.name: status for status in LeadStatus.objects.all()}


def status(name='New'):
    return ensure_statuses()[name]


class LeadSourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LeadSource
        django_get_or_create = ('name',)

    name = 'Website'


class LeadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Lead

    name = factory.Faker('company')
    contact_name = factory.Faker('name')
    email = factory.Faker('company_email')
    status = factory.LazyFunction(status)
