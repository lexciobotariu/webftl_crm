from django.http import QueryDict

from apps.tasks.viewspec import DEFAULT_LIMIT, LIMIT_STEP, TaskViewOptions, TaskViewSpec

OPTIONS = TaskViewOptions(
    status_ids=frozenset({1, 2, 3}),
    assignee_ids=frozenset({10, 11}),
    label_ids=frozenset({5, 6}),
)


def parse(query='', options=OPTIONS):
    return TaskViewSpec.from_params(QueryDict(query), options)


class TestDefaults:
    def test_empty_params_give_the_default_view(self):
        spec = parse()
        assert spec.layout == 'list'
        assert spec.hidden_statuses == frozenset()
        assert spec.priorities == ()
        assert spec.assignees == ()
        assert spec.labels == ()
        assert spec.q == ''
        assert spec.group == 'status'
        assert spec.sort == 'priority'
        assert spec.dir == 'asc'
        assert spec.limit == DEFAULT_LIMIT

    def test_default_view_serialises_to_just_the_layout(self):
        assert parse().to_params() == {'layout': 'list'}
        assert parse().to_query_string() == 'layout=list'

    def test_is_default_ignores_q_and_limit(self):
        assert parse('q=abc&limit=400').is_default
        assert not parse('group=assignee').is_default
        assert not parse('hide_status=1').is_default


class TestParsing:
    def test_reads_every_field(self):
        spec = parse(
            'layout=list&hide_status=2&hide_status=3&priority=urgent&priority=none'
            '&assignee=10&assignee=none&label=6&q=  hello  &group=priority&sort=due'
            '&dir=desc&limit=400'
        )
        assert spec.hidden_statuses == frozenset({2, 3})
        assert spec.priorities == ('urgent', 'none')
        assert spec.assignees == ('none', '10')
        assert spec.labels == (6,)
        assert spec.q == 'hello'
        assert spec.group == 'priority'
        assert spec.sort == 'due'
        assert spec.dir == 'desc'
        assert spec.limit == 400

    def test_unknown_values_are_ignored_not_errors(self):
        spec = parse(
            'layout=carousel&hide_status=99&hide_status=abc&priority=critical'
            '&assignee=77&assignee=x&label=404&group=colour&sort=mood&dir=sideways&limit=-5'
        )
        assert spec == parse()

    def test_ids_are_checked_against_the_options_given(self):
        narrow = TaskViewOptions(
            status_ids=frozenset({1}), assignee_ids=frozenset(), label_ids=frozenset()
        )
        spec = TaskViewSpec.from_params(
            QueryDict('hide_status=1&hide_status=2&assignee=10&label=5'), narrow
        )
        assert spec.hidden_statuses == frozenset({1})
        assert spec.assignees == ()
        assert spec.labels == ()

    def test_limit_is_clamped_and_rounded_to_a_step(self):
        assert parse('limit=1').limit == DEFAULT_LIMIT
        assert parse('limit=250').limit == DEFAULT_LIMIT + LIMIT_STEP
        assert parse('limit=99999999').limit == 5000
        assert parse('limit=abc').limit == DEFAULT_LIMIT

    def test_q_is_trimmed_and_capped(self):
        assert parse('q=%20%20').q == ''
        assert len(parse('q=' + 'a' * 500).q) == 100

    def test_plain_dicts_work_too(self):
        spec = TaskViewSpec.from_params(
            {'hide_status': ['1'], 'priority': 'high', 'group': 'none'}, OPTIONS
        )
        assert spec.hidden_statuses == frozenset({1})
        assert spec.priorities == ('high',)
        assert spec.group == 'none'

    def test_default_direction_follows_the_sort(self):
        assert parse('sort=created').dir == 'desc'
        assert parse('sort=updated').dir == 'desc'
        assert parse('sort=title').dir == 'asc'
        assert parse('sort=created&dir=asc').dir == 'asc'

    def test_filter_form_checked_statuses_become_hidden_ones(self):
        spec = parse('filter=1&shown_status=1&shown_status=3')
        assert spec.hidden_statuses == frozenset({2})

    def test_filter_form_with_nothing_checked_is_no_status_filter(self):
        assert parse('filter=1').hidden_statuses == frozenset()

    def test_filter_form_all_priorities_checked_is_no_filter(self):
        query = 'filter=1&' + '&'.join(
            f'priority={p}' for p in ('low', 'medium', 'high', 'urgent', 'none')
        )
        assert parse(query).priorities == ()

    def test_clear_drops_filters_but_keeps_display_choices(self):
        spec = parse(
            'clear=1&hide_status=1&priority=high&assignee=10&label=5&q=x&group=assignee&sort=due'
        )
        assert spec.hidden_statuses == frozenset()
        assert spec.priorities == ()
        assert spec.assignees == ()
        assert spec.labels == ()
        assert spec.group == 'assignee'
        assert spec.sort == 'due'


class TestRoundTrip:
    def test_to_params_round_trips(self):
        spec = parse(
            'hide_status=3&hide_status=1&priority=high&assignee=10&assignee=none&label=5'
            '&q=fix&group=assignee&sort=title&dir=desc&limit=400'
        )
        assert parse(spec.to_query_string()) == spec

    def test_canonical_form_is_stable_and_minimal(self):
        spec = parse('hide_status=3&hide_status=1&priority=urgent&group=status&sort=priority')
        assert spec.to_params() == {
            'layout': 'list',
            'hide_status': ['1', '3'],
            'priority': ['urgent'],
        }

    def test_non_default_display_choices_are_serialised(self):
        params = parse('group=assignee&sort=created&dir=asc&q=x&limit=400').to_params()
        assert params == {
            'layout': 'list', 'group': 'assignee', 'sort': 'created', 'dir': 'asc',
            'q': 'x', 'limit': '400',
        }

    def test_assignee_none_sorts_first(self):
        assert parse('assignee=11&assignee=none&assignee=10').to_params()['assignee'] == [
            'none', '10', '11',
        ]

    def test_replace_changes_one_field(self):
        spec = parse('group=assignee').replace(limit=400)
        assert spec.group == 'assignee'
        assert spec.limit == 400

    def test_saved_params_leave_out_search_and_paging(self):
        assert parse('hide_status=1&q=abc&limit=400').to_saved_params() == {
            'layout': 'list', 'hide_status': ['1'],
        }


class TestBoardLayout:
    def test_board_layout_is_accepted_and_serialised(self):
        spec = parse('layout=board')
        assert spec.layout == 'board'
        assert spec.to_params() == {'layout': 'board'}
        assert parse(spec.to_query_string()) == spec

    def test_board_is_not_the_default_view(self):
        assert not parse('layout=board').is_default

    def test_filters_are_kept_when_the_layout_changes(self):
        spec = parse('layout=board&hide_status=2&priority=high')
        assert spec.hidden_statuses == frozenset({2})
        assert spec.priorities == ('high',)


ALL_CATEGORIES = frozenset({'backlog', 'unstarted', 'started', 'completed', 'canceled'})
OPEN_CATEGORIES = frozenset({'backlog', 'unstarted', 'started'})
# The shape My Tasks gives the spec: list only, grouped by project, open tasks first.
MY_OPTIONS = TaskViewOptions(
    layouts=('list',),
    groups=('project', 'category', 'priority', 'none'),
    categories=ALL_CATEGORIES,
    has_assignee_filter=False,
    default_group='project',
    default_categories=OPEN_CATEGORIES,
)


def parse_my(query=''):
    return parse(query, MY_OPTIONS)


class TestPageOptions:
    def test_project_page_options_are_the_defaults(self):
        options = TaskViewOptions()
        assert options.layouts == ('list', 'board')
        assert options.groups == ('status', 'assignee', 'priority', 'none')
        assert options.categories == frozenset()
        assert options.has_assignee_filter
        assert options.default_group == 'status'
        assert options.default_categories == frozenset()

    def test_layouts_limit_what_the_url_may_ask_for(self):
        assert parse_my('layout=board').layout == 'list'
        assert parse_my('layout=board').to_params()['layout'] == 'list'

    def test_groups_limit_what_the_url_may_ask_for(self):
        assert parse('group=project').group == 'status'
        assert parse('group=category').group == 'status'
        assert parse_my('group=status').group == 'project'
        assert parse_my('group=assignee').group == 'project'
        assert parse_my('group=category').group == 'category'

    def test_assignee_none_needs_the_assignee_filter(self):
        assert parse_my('assignee=none').assignees == ()
        assert parse('assignee=none').assignees == ('none',)

    def test_options_do_not_take_part_in_equality(self):
        other = TaskViewOptions(status_ids=frozenset({9}))
        assert parse('group=none') == parse('group=none', other)
        assert 'options' not in repr(parse())


class TestCategories:
    def test_page_without_category_filter_ignores_the_parameter(self):
        spec = parse('category=completed&filter=1&shown_category=completed')
        assert spec.categories == frozenset()
        assert 'category' not in spec.to_params()

    def test_absent_means_the_pages_default(self):
        assert parse_my().categories == OPEN_CATEGORIES

    def test_explicit_categories_mean_exactly_those(self):
        spec = parse_my('category=completed&category=canceled')
        assert spec.categories == {'completed', 'canceled'}

    def test_all_five_mean_everything_and_are_not_collapsed(self):
        query = '&'.join(f'category={c}' for c in ALL_CATEGORIES)
        spec = parse_my(query)
        assert spec.categories == ALL_CATEGORIES
        assert sorted(spec.to_params()['category']) == sorted(ALL_CATEGORIES)
        assert parse_my(spec.to_query_string()) == spec

    def test_unknown_categories_are_dropped(self):
        assert parse_my('category=done&category=started').categories == {'started'}
        assert parse_my('category=done').categories == OPEN_CATEGORIES

    def test_serialised_in_the_order_of_the_status_types(self):
        spec = parse_my('category=canceled&category=backlog&category=completed')
        assert spec.to_params()['category'] == ['backlog', 'completed', 'canceled']

    def test_default_categories_are_left_out_of_the_url(self):
        spec = parse_my('category=started&category=backlog&category=unstarted')
        assert 'category' not in spec.to_params()
        assert spec.to_params() == {'layout': 'list'}

    def test_default_group_is_left_out_of_the_url(self):
        assert parse_my('group=project').to_params() == {'layout': 'list'}
        assert parse_my('group=category').to_params()['group'] == 'category'
        # The project page's own default is an explicit choice here.
        assert parse_my('group=priority').to_params()['group'] == 'priority'

    def test_filter_form_checked_types_become_the_selection(self):
        spec = parse_my('filter=1&shown_category=completed&shown_category=started')
        assert spec.categories == {'completed', 'started'}

    def test_filter_form_with_nothing_checked_is_the_default(self):
        assert parse_my('filter=1').categories == OPEN_CATEGORIES

    def test_clear_goes_back_to_the_default_not_to_everything(self):
        spec = parse_my('clear=1&category=completed&group=category&priority=high')
        assert spec.categories == OPEN_CATEGORIES
        assert spec.priorities == ()
        assert spec.group == 'category'

    def test_is_default_is_measured_against_the_page(self):
        assert parse_my().is_default
        assert parse_my('q=abc&limit=400').is_default
        assert not parse_my('category=completed').is_default
        assert not parse_my('group=none').is_default
        assert not parse_my('priority=high').is_default

    def test_filter_count_counts_differences_from_the_default(self):
        assert parse_my().filter_count == 0
        assert not parse_my().has_filters
        assert parse_my('category=completed').filter_count == 1
        assert parse_my('category=completed').has_filters
        assert parse_my('category=completed&priority=high').filter_count == 2
        # Display choices are not filters.
        assert parse_my('group=none').filter_count == 0

    def test_round_trip(self):
        spec = parse_my('category=completed&category=started&group=category&priority=high&q=x')
        assert parse_my(spec.to_query_string()) == spec

    def test_replace_keeps_the_page_options(self):
        assert parse_my().replace(limit=400).to_params() == {'layout': 'list', 'limit': '400'}
