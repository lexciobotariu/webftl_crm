"""Search across what a person may open: tasks, projects, clients, and pages.

Each section applies the same visibility rule as the page that lists it, and is
left out entirely when the person does not have the module. The visibility
helpers do not check the module themselves.
"""
import re
from dataclasses import dataclass, field

from django.db.models import Case, IntegerField, Q, Value, When

from apps.clients.models import visible_clients
from apps.projects.models import visible_projects
from apps.tasks.models import visible_tasks
from apps.tasks.viewspec import MAX_QUERY_LENGTH

from .pages import pages_for

MIN_QUERY_LENGTH = 2
PER_SECTION = 5
# "19" or "CUST-19": the prefix is only how a task id is shown, so it is ignored.
TASK_ID = re.compile(r'^(?:[A-Za-z0-9]+-)?(\d{1,9})$')


@dataclass
class SearchResults:
    query: str
    too_short: bool = False
    tasks: list = field(default_factory=list)
    projects: list = field(default_factory=list)
    clients: list = field(default_factory=list)
    pages: list = field(default_factory=list)

    @property
    def empty(self):
        return not (self.tasks or self.projects or self.clients or self.pages)


def clean_query(raw):
    return (raw or '').strip()[:MAX_QUERY_LENGTH]


def search(user, raw_query):
    query = clean_query(raw_query)
    results = SearchResults(query=query)
    if len(query) < MIN_QUERY_LENGTH:
        results.too_short = True
        return results

    if user.has_app_permission('access_tasks'):
        condition = Q(title__icontains=query)
        match = TASK_ID.match(query)
        number = int(match.group(1)) if match else None
        if number is not None:
            condition |= Q(pk=number)
        tasks = visible_tasks(user).filter(condition).select_related('project', 'status')
        if number is not None:
            # An id typed in full comes first.
            tasks = tasks.annotate(
                exact=Case(When(pk=number, then=Value(0)), default=Value(1), output_field=IntegerField())
            ).order_by('exact', '-updated_at')
        else:
            tasks = tasks.order_by('-updated_at')
        results.tasks = list(tasks[:PER_SECTION])

    if user.has_app_permission('access_projects'):
        results.projects = list(
            visible_projects(user).filter(name__icontains=query).select_related('client').order_by('name')[:PER_SECTION]
        )

    if user.has_app_permission('access_clients'):
        results.clients = list(visible_clients(user).filter(name__icontains=query).order_by('name')[:PER_SECTION])

    needle = query.lower()
    results.pages = [page for page in pages_for(user) if needle in page.label.lower()][:PER_SECTION]
    return results
