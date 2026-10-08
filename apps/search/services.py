"""Search across what a person may open: tasks, projects, clients, and pages.

Each section applies the same visibility rule as the page that lists it, and is
left out entirely when the person does not have the module. The visibility
helpers do not check the module themselves.
"""
import re
from dataclasses import dataclass, field

from django.db.models import Case, IntegerField, Q, Value, When

from apps.clients.models import active_clients, visible_clients
from apps.projects.models import Project, visible_projects
from apps.tasks.models import visible_tasks
from apps.tasks.viewspec import MAX_QUERY_LENGTH

from .pages import pages_for

MIN_QUERY_LENGTH = 2
PER_SECTION = 5
# "CUST-19" is task 19 of the project whose key is CUST; "19" is task 19 of any
# project. Keys are stored in capitals, so "cust-19" works too.
TASK_ID = re.compile(r'^(?:([A-Za-z][A-Za-z0-9]{1,5})-)?(\d{1,9})$')


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
    match = TASK_ID.match(query)
    id_query = None
    if match:
        id_query = Q(number=int(match.group(2)))
        if match.group(1):
            id_query &= Q(project__key=match.group(1).upper())
    # One character is too little to search names by, but "7" is a whole task id.
    id_only = len(query) < MIN_QUERY_LENGTH
    if id_only and id_query is None:
        results.too_short = True
        return results

    if user.has_app_permission('access_tasks'):
        if id_only:
            condition = id_query
        else:
            condition = Q(title__icontains=query)
            if id_query is not None:
                condition |= id_query
        tasks = visible_tasks(user).filter(condition).select_related('project', 'status')
        if id_query is not None:
            # An id typed in full comes first.
            tasks = tasks.annotate(
                exact=Case(When(id_query, then=Value(0)), default=Value(1), output_field=IntegerField())
            ).order_by('exact', '-updated_at')
        else:
            tasks = tasks.order_by('-updated_at')
        results.tasks = list(tasks[:PER_SECTION])
    if id_only:
        return results

    if user.has_app_permission('access_projects'):
        results.projects = list(
            # Finished and cancelled projects stay out, as on the projects page.
            visible_projects(user)
            .filter(name__icontains=query, status__in=Project.OPEN_STATUSES)
            .select_related('client')
            .order_by('name')[:PER_SECTION]
        )

    if user.has_app_permission('access_clients'):
        # Archived clients stay out, as on the client list. A contact's name or email finds its client.
        matching = Q(name__icontains=query) | Q(contacts__name__icontains=query) | Q(contacts__email__icontains=query)
        results.clients = list(
            active_clients(visible_clients(user)).filter(matching).distinct().order_by('name')[:PER_SECTION]
        )

    needle = query.lower()
    results.pages = [page for page in pages_for(user) if needle in page.label.lower()][:PER_SECTION]
    return results
