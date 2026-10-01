"""Project keys: the short prefix in a task id such as ``CUST-12``.

Kept free of model imports, because the data migration that gives existing
projects their keys calls the same function.
"""
import re
import unicodedata

KEY_MAX_LENGTH = 6
KEY_REGEX = r'^[A-Z][A-Z0-9]{1,5}$'
BASE_LENGTH = 4


def _base(name, pk):
    ascii_name = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode()
    chars = re.sub(r'[^A-Za-z0-9]', '', ascii_name).upper().lstrip('0123456789')
    if chars:
        return chars[:BASE_LENGTH].ljust(2, 'X')
    if pk is not None:
        return f'P{pk}'[:KEY_MAX_LENGTH]
    return 'PX'


def derive_key(name, taken, pk=None):
    """A free key for a project called ``name``.

    The first four ASCII letters and digits of the name, starting at the first
    letter ("ÉLAN Studio" is ``ELAN``), padded with ``X`` to two characters. A
    name with no letters falls back to ``P<pk>``. A key in ``taken`` gets a
    numeric suffix, shortening the base so the result stays within six
    characters (``CUST2`` ... ``CUST99``, ``CUS100``).
    """
    base = _base(name, pk)
    if base not in taken:
        return base
    suffix = 2
    while True:
        digits = str(suffix)
        candidate = base[:KEY_MAX_LENGTH - len(digits)] + digits
        if candidate not in taken:
            return candidate
        suffix += 1
