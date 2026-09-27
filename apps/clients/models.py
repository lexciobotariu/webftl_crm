from django.db import models


class Client(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def project_count(self):
        return self.projects.count()


def visible_clients(user):
    """Clients this user may see on the dashboard and in the client list.

    ``clients_view_all`` is every client. Without it, the distinct clients of
    projects where ``user`` has a membership. ``role=admin`` bypasses the flag
    through ``User.has_app_permission``.

    Membership is filtered through a primary-key subquery so two projects on
    the same client still count as one client.
    """
    if user.has_app_permission('clients_view_all'):
        return Client.objects.all()
    from apps.projects.models import ProjectMember

    client_ids = ProjectMember.objects.filter(user=user).values('project__client_id')
    return Client.objects.filter(pk__in=client_ids)
