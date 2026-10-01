"""The pages the command palette can open.

This is the sidebar's list with the sidebar's conditions
(``templates/components/sidebar.html``); a test renders the sidebar for several
kinds of user and checks the two agree. Add a sidebar entry here too.
"""
from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class Page:
    label: str
    url_name: str
    # A permission key the user must have, 'admin' for admins only, or None for everyone.
    requires: str | None = None

    def allowed_for(self, user):
        if self.requires is None:
            return True
        if self.requires == 'admin':
            return user.is_admin
        return user.has_app_permission(self.requires)

    @property
    def url(self):
        return reverse(self.url_name)


PAGES = (
    Page('Dashboard', 'dashboard', 'access_dashboard'),
    Page('Clients', 'client_list', 'access_clients'),
    Page('Projects', 'project_list', 'access_projects'),
    Page('My Tasks', 'my_tasks', 'access_tasks'),
    Page('My Week', 'time_week', 'access_tasks'),
    Page('Salaries', 'salary_list', 'access_salaries'),
    Page('Invoices', 'invoice_list', 'access_invoices'),
    Page('Team', 'team_list', 'access_team'),
    Page('Settings', 'settings', 'admin'),
    Page('Changelog', 'changelog'),
)


def pages_for(user):
    """The pages ``user`` sees in the sidebar."""
    return [page for page in PAGES if page.allowed_for(user)]
