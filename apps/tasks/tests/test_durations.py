import pytest

from apps.tasks.durations import MAX_MINUTES, format_minutes, parse_duration


@pytest.mark.parametrize('text, minutes', [
    ('1h 30m', 90),
    ('1h30m', 90),
    ('1h30', 90),
    ('90m', 90),
    ('1.5h', 90),
    ('1,5h', 90),
    ('1:30', 90),
    ('0:45', 45),
    ('2H', 120),
    ('  45M ', 45),
    ('2h 0m', 120),
    ('0.25h', 15),
    ('1h 30', 90),
    ('1.33h', 80),
])
def test_parse_duration_accepts(text, minutes):
    assert parse_duration(text) == minutes


@pytest.mark.parametrize('text', [
    '-1h', '1:75', '1:30:00', '1d', '1e3', '', '   ', 'abc', 'h', '1h 30m 10m', '0m', '0:00', '0h',
    '١٢h', '٣٠m', '1.5.5h', '1.5m', '0.005h',
])
def test_parse_duration_rejects(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_bare_number_means_hours_only_when_allowed():
    assert parse_duration('4', bare_unit='hours') == 240
    assert parse_duration('1.5', bare_unit='hours') == 90
    with pytest.raises(ValueError, match='30m or 2h'):
        parse_duration('15')


def test_parse_duration_has_an_upper_bound():
    with pytest.raises(ValueError):
        parse_duration(f'{MAX_MINUTES + 1}m')
    with pytest.raises(ValueError):
        parse_duration('9' * 400 + 'h')
    assert parse_duration(f'{MAX_MINUTES}m') == MAX_MINUTES


@pytest.mark.parametrize('minutes, label', [
    (90, '1h 30m'),
    (45, '45m'),
    (120, '2h'),
    (1, '1m'),
    (0, '<1m'),
    (605, '10h 5m'),
])
def test_format_minutes(minutes, label):
    assert format_minutes(minutes) == label


def test_format_minutes_empty():
    assert format_minutes(None) == ''
    assert format_minutes(None, empty='—') == '—'


def test_round_trip():
    for n in [1, 5, 59, 60, 61, 90, 480, 1439, 1440, 6000]:
        assert parse_duration(format_minutes(n)) == n


class TestVeryLongNumbers:
    def test_a_number_too_long_for_the_arithmetic_is_refused_not_an_error(self):
        import pytest as _pytest

        from apps.tasks.durations import parse_duration

        for text in ('9' * 28 + 'h', '9' * 30):
            with _pytest.raises(ValueError, match='at most'):
                parse_duration(text, bare_unit='hours')
