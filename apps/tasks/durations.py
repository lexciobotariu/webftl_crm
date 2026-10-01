"""Parsing and formatting of durations written as free text ("1h 30m").

Durations are stored as whole minutes. Every place that shows or accepts one
goes through this module so the format stays the same everywhere.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

MAX_MINUTES = 1000 * 60  # 1000 hours; keeps absurd input out of the database
_MAX_INPUT_LENGTH = 32

_COLON = re.compile(r'([0-9]+):([0-9]{2})')
_UNITS = re.compile(r'(?:([0-9]+(?:[.,][0-9]+)?)\s*h)?\s*(?:([0-9]+)\s*(m)?)?', re.IGNORECASE)
_BARE = re.compile(r'[0-9]+(?:[.,][0-9]+)?')

BARE_HINT = 'Add a unit, like 30m or 2h.'


def parse_duration(text, *, bare_unit=None):
    """Return whole minutes for `text`, or raise ValueError with a user-facing message.

    `bare_unit='hours'` makes a number without a unit mean hours (the estimate
    field); otherwise a bare number is refused, so "15" can't log 15 hours.
    """
    text = (text or '').strip()
    if not text:
        raise ValueError('Enter a duration, like 1h 30m.')
    if len(text) > _MAX_INPUT_LENGTH:
        raise ValueError('That duration is too long.')

    minutes = _to_minutes(text, bare_unit)
    if minutes is None:
        raise ValueError('Use hours and minutes, like 1h 30m, 45m or 1.5h.')
    if minutes < 1:
        raise ValueError('The duration must be at least 1 minute.')
    if minutes > MAX_MINUTES:
        raise ValueError(f'The duration can be at most {format_minutes(MAX_MINUTES)}.')
    return minutes


def _to_minutes(text, bare_unit):
    if match := _COLON.fullmatch(text):
        hours, mins = int(match[1]), int(match[2])
        return hours * 60 + mins if mins < 60 else None

    if _BARE.fullmatch(text):
        if bare_unit != 'hours':
            raise ValueError(BARE_HINT)
        return _round_minutes(Decimal(text.replace(',', '.')) * 60)

    match = _UNITS.fullmatch(text)
    if not match or not (match[1] or match[2]):
        return None
    hours, mins, minutes_unit = match[1], match[2], match[3]
    # "1h30" may drop the trailing "m"; a lone number needs it (bare numbers were handled above).
    if mins and not hours and not minutes_unit:
        return None
    total = Decimal(hours.replace(',', '.')) * 60 if hours else Decimal(0)
    total += int(mins) if mins else 0
    return _round_minutes(total)


def _round_minutes(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_seconds(seconds, *, zero='<1m'):
    """Whole minutes of `seconds`, in the same shape; `zero` stands for no time at all."""
    seconds = int(seconds)
    if seconds <= 0:
        return zero
    return format_minutes(seconds // 60)


def format_minutes(minutes, *, empty=''):
    """`90` -> "1h 30m", `45` -> "45m", `120` -> "2h", `0` -> "<1m"."""
    if minutes is None:
        return empty
    if minutes < 1:
        return '<1m'
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f'{hours}h {mins}m'
    return f'{hours}h' if hours else f'{mins}m'
