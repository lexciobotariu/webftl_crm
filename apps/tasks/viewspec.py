"""The state of a project's Tasks page, read from and written to the URL.

``TaskViewSpec`` is the one place that knows which query parameters exist and
what they may contain. The list layout (and the board, later) only ever see a
validated spec, so a stale bookmark or a hand-edited URL degrades to the default
view instead of erroring.

Options come in as an argument rather than from a project, so the same spec can
drive a view that is not scoped to one project (My Tasks).
"""
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode

from apps.projects.models import Status

from .models import priorities_to_store

LAYOUTS = ('list', 'board')
# Status types in their natural order; the position in this tuple is the order
# they are listed in the URL and in the filter.
CATEGORIES = tuple(value for value, _label in Status.CATEGORY_CHOICES)
START_CHOICES = (
    ('', 'Any'),
    ('started', 'Started'),
    ('later', 'Not started yet'),
)
START_VALUES = tuple(value for value, _ in START_CHOICES)

SORT_CHOICES = (
    ('manual', 'Manual'),
    ('priority', 'Priority'),
    ('due', 'Due date'),
    ('created', 'Created'),
    ('updated', 'Updated'),
    ('title', 'Title'),
)
SORTS = tuple(value for value, _label in SORT_CHOICES)
DIRECTIONS = ('asc', 'desc')
# "asc" means the natural order of the key: most urgent first, earliest due
# date first, oldest first, A to Z. Dates of activity read better newest first.
# "Manual" is the order cards were dragged into on the board.
DEFAULT_DIR = {
    'manual': 'asc',
    'priority': 'asc',
    'due': 'asc',
    'created': 'desc',
    'updated': 'desc',
    'title': 'asc',
}
ASSIGNEE_NONE = 'none'
# What a list row can show besides its title, status, priority and assignee, in row
# order. ``col=none`` in the URL means "none of them".
COLUMN_CHOICES = (
    ('id', 'ID'),
    ('project', 'Project'),
    ('labels', 'Labels'),
    ('due', 'Due date'),
    ('estimate', 'Estimate'),
)
COLUMNS = tuple(value for value, _label in COLUMN_CHOICES)
COLUMNS_NONE = 'none'

DEFAULT_LIMIT = 200
LIMIT_STEP = 200
MAX_LIMIT = 5000
MAX_QUERY_LENGTH = 100


def sort_choices(options=None):
    """``(value, label, default direction)`` for the Display menu.

    The template reads the default direction from here, so the menu and the
    server can never disagree about what "no ``dir``" means for a sort. Only the
    sorts ``options`` allows are listed.
    """
    allowed = options.sorts if options is not None else SORTS
    return [(value, label, DEFAULT_DIR[value]) for value, label in SORT_CHOICES if value in allowed]


def column_choices(spec):
    """``(value, label, shown)`` for the Display menu's row properties, as the page allows."""
    return [
        (value, label, value in spec.columns)
        for value, label in COLUMN_CHOICES
        if value in spec.options.columns
    ]


def default_sort(group, options):
    """Grouped by status, the list follows the board's manual order by default."""
    if group == 'status' and 'manual' in options.sorts:
        return 'manual'
    return 'priority'


def default_show_empty(group):
    """Status columns are a fixed set, so they stay visible when empty; other groups do not."""
    return group == 'status'


@dataclass(frozen=True)
class TaskViewOptions:
    """What a page lets its URL say; anything else in the URL is dropped.

    The ids are the rows the view may refer to. The rest is the shape of the page
    itself: which layouts and groupings it offers, whether it filters by status
    type (``categories`` is the allowed set, empty for a page without that filter)
    or by assignee, and what it shows when the URL says nothing. The defaults are
    the project Tasks page.
    """

    status_ids: frozenset = frozenset()
    assignee_ids: frozenset = frozenset()
    label_ids: frozenset = frozenset()
    layouts: tuple = LAYOUTS
    groups: tuple = ('status', 'assignee', 'priority', 'none')
    sorts: tuple = SORTS
    columns: frozenset = frozenset({'id', 'labels', 'due', 'estimate'})
    default_columns: frozenset = frozenset({'id', 'labels', 'due'})
    categories: frozenset = frozenset()
    has_assignee_filter: bool = True
    default_group: str = 'status'
    default_categories: frozenset = frozenset()


def _getlist(params, key):
    if hasattr(params, 'getlist'):
        return params.getlist(key)
    value = params.get(key)
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else [value]


def _getone(params, key):
    values = _getlist(params, key)
    return values[-1] if values else None


def _ids(values, allowed):
    found = set()
    for raw in values:
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number in allowed:
            found.add(number)
    return found


def _choice(value, allowed, default):
    return value if value in allowed else default


def _limit(raw):
    try:
        wanted = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    if wanted <= DEFAULT_LIMIT:
        return DEFAULT_LIMIT
    wanted = min(wanted, MAX_LIMIT)
    steps = -(-(wanted - DEFAULT_LIMIT) // LIMIT_STEP)
    return min(DEFAULT_LIMIT + steps * LIMIT_STEP, MAX_LIMIT)


@dataclass(frozen=True)
class TaskViewSpec:
    layout: str = 'list'
    hidden_statuses: frozenset = frozenset()
    priorities: tuple = ()
    assignees: tuple = ()
    labels: tuple = ()
    q: str = ''
    group: str = 'status'
    sort: str = 'manual'
    dir: str = 'asc'
    # Groups with no task are listed too (with zero), so a status can be seen empty.
    show_empty: bool = True
    # Which optional row columns show (COLUMNS); see ``TaskViewOptions.default_columns``.
    columns: frozenset = frozenset({'id', 'labels', 'due'})
    limit: int = DEFAULT_LIMIT
    categories: frozenset = frozenset()
    # Closed tasks past TASK_ARCHIVE_AFTER_DAYS are left out unless this is on.
    archived: bool = False
    # START_CHOICES: '' for any, 'started' (no start date or one today or earlier),
    # 'later' (a start date after today).
    start: str = ''
    # Carried so ``to_params`` and ``is_default`` can tell what the page's defaults
    # are. Not part of the state itself, so it stays out of equality and repr.
    options: TaskViewOptions = field(default_factory=TaskViewOptions, compare=False, repr=False)

    @classmethod
    def from_params(cls, params, options):
        """Validate ``params`` (a QueryDict or a plain dict) against ``options``.

        Two spellings of the status filter are accepted. ``hide_status`` is the
        canonical one: statuses are stored as the ones left out, so a status
        added later shows up by itself. The filter form posts the checked ones
        as ``shown_status`` together with ``filter=1``, and is translated here.
        The type filter is positive: ``category`` (or ``shown_category`` with
        ``filter=1``) lists exactly the status types to show, and leaving it out
        means the page's default. All of them checked is kept as it is, not folded
        into "no filter". ``clear=1`` drops every filter, back to the page's
        default, and keeps the display choices.
        """
        clearing = _getone(params, 'clear') == '1'

        if _getone(params, 'filter') == '1':
            shown = _ids(_getlist(params, 'shown_status'), options.status_ids)
            hidden = set(options.status_ids) - shown if shown else set()
        else:
            hidden = _ids(_getlist(params, 'hide_status'), options.status_ids)

        if not options.categories:
            categories = frozenset()
        else:
            key = 'shown_category' if _getone(params, 'filter') == '1' else 'category'
            categories = frozenset(_getlist(params, key)) & options.categories
            categories = categories or options.default_categories

        raw_assignees = _getlist(params, 'assignee')
        raw_assignees = [
            raw for raw in raw_assignees if options.has_assignee_filter or raw != ASSIGNEE_NONE
        ]
        assignee_ids = _ids(
            [raw for raw in raw_assignees if raw != ASSIGNEE_NONE], options.assignee_ids
        )
        assignee_tokens = tuple(
            ([ASSIGNEE_NONE] if ASSIGNEE_NONE in raw_assignees else [])
            + [str(pk) for pk in sorted(assignee_ids)]
        )

        group = _choice(_getone(params, 'group'), options.groups, options.default_group)
        sort = _choice(_getone(params, 'sort'), options.sorts, default_sort(group, options))
        empty = _getone(params, 'empty')
        show_empty = empty == '1' if empty in ('0', '1') else default_show_empty(group)
        # The Display form always sends ``cols=1`` with its checkboxes, so there none
        # checked means none; in a URL, no ``col`` means the page's default.
        raw_columns = _getlist(params, 'col')
        columns = frozenset(raw_columns) & options.columns
        if not columns and COLUMNS_NONE not in raw_columns and _getone(params, 'cols') != '1':
            columns = options.default_columns
        spec = cls(
            layout=_choice(_getone(params, 'layout'), options.layouts, options.layouts[0]),
            hidden_statuses=frozenset(hidden),
            priorities=tuple(priorities_to_store(_getlist(params, 'priority'))),
            assignees=assignee_tokens,
            labels=tuple(sorted(_ids(_getlist(params, 'label'), options.label_ids))),
            q=(_getone(params, 'q') or '').strip()[:MAX_QUERY_LENGTH],
            group=group,
            sort=sort,
            dir=_choice(_getone(params, 'dir'), DIRECTIONS, DEFAULT_DIR[sort]),
            show_empty=show_empty,
            columns=columns,
            limit=_limit(_getone(params, 'limit')),
            categories=categories,
            archived=_getone(params, 'archived') == '1',
            start=_choice(_getone(params, 'start'), START_VALUES, ''),
            options=options,
        )
        if clearing:
            spec = replace(
                spec,
                hidden_statuses=frozenset(),
                priorities=(),
                assignees=(),
                labels=(),
                categories=frozenset(options.default_categories),
                archived=False,
                start='',
            )
        return spec

    def replace(self, **changes):
        return replace(self, **changes)

    @property
    def has_filters(self):
        return self.filter_count > 0

    @property
    def filter_count(self):
        """How many filter groups differ from the page's default (for the toolbar badge)."""
        return sum(
            bool(group)
            for group in (self.hidden_statuses, self.priorities, self.assignees, self.labels)
        ) + (self.categories != self.options.default_categories) + self.archived + bool(self.start)

    @property
    def is_default(self):
        """True when nothing but search text or paging differs from a fresh view."""
        return self.to_saved_params() == {'layout': self.options.layouts[0]}

    def to_params(self):
        """The canonical query parameters: defaults left out, ``layout`` always in.

        ``layout`` is always present so that only a bare query string means
        "restore the view this person last used".
        """
        params = {'layout': self.layout}
        if self.categories != self.options.default_categories:
            params['category'] = [value for value in CATEGORIES if value in self.categories]
        if self.hidden_statuses:
            params['hide_status'] = [str(pk) for pk in sorted(self.hidden_statuses)]
        if self.priorities:
            params['priority'] = list(self.priorities)
        if self.assignees:
            params['assignee'] = list(self.assignees)
        if self.labels:
            params['label'] = [str(pk) for pk in self.labels]
        if self.archived:
            params['archived'] = '1'
        if self.start:
            params['start'] = self.start
        if self.q:
            params['q'] = self.q
        if self.group != self.options.default_group:
            params['group'] = self.group
        if self.sort != default_sort(self.group, self.options):
            params['sort'] = self.sort
        if self.dir != DEFAULT_DIR[self.sort]:
            params['dir'] = self.dir
        if self.show_empty != default_show_empty(self.group):
            params['empty'] = '1' if self.show_empty else '0'
        if self.columns != self.options.default_columns:
            params['col'] = [value for value in COLUMNS if value in self.columns] or [COLUMNS_NONE]
        if self.limit != DEFAULT_LIMIT:
            params['limit'] = str(self.limit)
        return params

    def to_saved_params(self):
        """What is remembered per person and project: search and paging are not."""
        params = self.to_params()
        params.pop('q', None)
        params.pop('limit', None)
        return params

    def to_query_string(self):
        return urlencode(self.to_params(), doseq=True)
