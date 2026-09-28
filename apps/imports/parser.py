"""Stream a Perfex MySQL dump and keep the rows this import uses.

The dump is read line by line. INSERT statements for other tables are scanned
only far enough to find the closing semicolon, so session rows and templates
are never stored. String literals can contain semicolons and newlines.
"""

from decimal import Decimal

from django.core.management.base import CommandError

# Tables the importer reads. Everything else in the dump is ignored, including
# sessions, templates, logs, the vault, proposals, contracts, and portal settings.
WANTED_TABLES = frozenset({
    'tblstaff',
    'tbloptions',
    'tblcurrencies',
    'tblcountries',
    'tblclients',
    'tblcontacts',
    'tblprojects',
    'tbltasks',
    'tbltask_checklist_items',
    'tbltask_comments',
    'tbltaskstimers',
    'tblinvoices',
    'tblitemable',
    'tblinvoicepaymentrecords',
    'tblpayment_modes',
    'tblstaff_salaries',
    'tblstaff_salary_payments',
    'tblfiles',
})

_ESCAPES = {
    '0': '\0',
    'n': '\n',
    'r': '\r',
    't': '\t',
    'Z': '\x1a',
    '\\': '\\',
    "'": "'",
    '"': '"',
}


class _Chars:
    """A character cursor over a line iterator."""

    def __init__(self, lines):
        self._lines = iter(lines)
        self._buf = ''
        self._pos = 0
        self._eof = False

    def _fill(self):
        if self._eof:
            return False
        try:
            chunk = next(self._lines)
        except StopIteration:
            self._eof = True
            return False
        if self._pos:
            self._buf = self._buf[self._pos:]
            self._pos = 0
        self._buf += chunk
        return True

    def peek(self, size=1):
        while len(self._buf) - self._pos < size and self._fill():
            pass
        return self._buf[self._pos:self._pos + size]

    def get(self):
        char = self.peek(1)
        if not char:
            raise CommandError('The dump ended before a statement finished.')
        self._pos += 1
        return char


def read_dump(stream):
    """Return ``{table: [row, ...]}`` for :data:`WANTED_TABLES`."""
    tables = {name: [] for name in WANTED_TABLES}
    chars = _Chars(stream)
    if chars.peek(1) == '\ufeff':
        chars.get()
    while _skip_gap(chars):
        if chars.peek(1) == ';':
            chars.get()
            continue
        word = _read_keyword(chars)
        if word.upper() != 'INSERT':
            _skip_statement(chars)
            continue
        table, columns = _read_insert(chars)
        if table not in WANTED_TABLES:
            _skip_statement(chars)
            continue
        if not columns:
            raise CommandError(f'INSERT into {table} has no column list.')
        for row in _read_tuples(chars, table, columns):
            tables[table].append(row)
    return tables


def _skip_gap(chars):
    """Skip whitespace and comments. Return whether a statement character remains."""
    while True:
        char = chars.peek(1)
        if not char:
            return False
        if char.isspace():
            chars.get()
            continue
        if char == '#':
            _skip_line(chars)
            continue
        if chars.peek(2) == '--':
            third = chars.peek(3)
            if len(third) < 3 or third[2].isspace():
                _skip_line(chars)
                continue
        if chars.peek(2) == '/*':
            chars.get()
            chars.get()
            while chars.peek(2) != '*/':
                if not chars.peek(1):
                    raise CommandError('Unclosed block comment in the dump.')
                chars.get()
            chars.get()
            chars.get()
            continue
        return True


def _skip_line(chars):
    while True:
        char = chars.peek(1)
        if not char or char == '\n':
            if char:
                chars.get()
            return
        chars.get()


def _skip_ws(chars):
    while chars.peek(1).isspace():
        chars.get()


def _read_keyword(chars):
    _skip_ws(chars)
    letters = []
    while True:
        char = chars.peek(1)
        if not char or not (char.isalpha() or char == '_'):
            break
        letters.append(chars.get())
    if not letters:
        raise CommandError(f'Expected a word in the dump, found {chars.peek(1)!r}.')
    return ''.join(letters)


def _read_ident(chars):
    _skip_ws(chars)
    if chars.peek(1) == '`':
        chars.get()
        name = []
        while True:
            char = chars.get()
            if char == '`':
                if chars.peek(1) == '`':
                    chars.get()
                    name.append('`')
                    continue
                break
            name.append(char)
        return ''.join(name)
    name = []
    while True:
        char = chars.peek(1)
        if not char or not (char.isalnum() or char == '_'):
            break
        name.append(chars.get())
    if not name:
        raise CommandError('Expected a table or column name.')
    return ''.join(name)


def _read_insert(chars):
    """Consume ``INTO table (cols) VALUES``. ``INSERT`` is already consumed."""
    into = _read_keyword(chars)
    if into.upper() != 'INTO':
        raise CommandError('Expected INSERT INTO.')
    table = _read_ident(chars)
    _skip_ws(chars)
    if chars.peek(1) == '.':
        chars.get()
        table = _read_ident(chars)
    _skip_ws(chars)
    columns = _read_column_list(chars) if chars.peek(1) == '(' else []
    keyword = _read_keyword(chars)
    if keyword.upper() != 'VALUES':
        raise CommandError(f'Expected VALUES after INSERT INTO {table}.')
    return table.lower(), [column.lower() for column in columns]


def _read_column_list(chars):
    chars.get()
    columns = []
    while True:
        _skip_ws(chars)
        if chars.peek(1) == ')':
            chars.get()
            return columns
        if chars.peek(1) == ',':
            chars.get()
            continue
        columns.append(_read_ident(chars))


def _read_tuples(chars, table, columns):
    while True:
        _skip_ws(chars)
        char = chars.peek(1)
        if char in ('', ';'):
            if char == ';':
                chars.get()
            return
        if char == ',':
            chars.get()
            continue
        if char != '(':
            raise CommandError(f'Unexpected {char!r} in {table} values.')
        chars.get()
        values = _read_row(chars, table)
        if len(values) != len(columns):
            raise CommandError(
                f'{table} has {len(values)} values for {len(columns)} columns.'
            )
        yield dict(zip(columns, values, strict=True))


def _read_row(chars, table):
    values = []
    while True:
        _skip_ws(chars)
        char = chars.peek(1)
        if char == "'":
            chars.get()
            values.append(_read_string(chars))
        elif char in (',', ')'):
            raise CommandError(f'{table} is missing a value.')
        else:
            values.append(_read_atom(chars, table))
        _skip_ws(chars)
        char = chars.peek(1)
        if char == ',':
            chars.get()
            continue
        if char == ')':
            chars.get()
            return values
        raise CommandError(f'Expected a comma or the end of a {table} row, found {char!r}.')


def _read_string(chars):
    """Decode a MySQL string. The opening quote is already consumed."""
    out = []
    while True:
        char = chars.get()
        if char == '\\':
            escaped = chars.get()
            out.append(_ESCAPES.get(escaped, escaped))
            continue
        if char == "'":
            if chars.peek(1) == "'":
                chars.get()
                out.append("'")
                continue
            return ''.join(out)
        out.append(char)


def _read_atom(chars, table):
    token = []
    while True:
        char = chars.peek(1)
        if not char or char in ',);\n\r\t ':
            break
        token.append(chars.get())
    text = ''.join(token)
    if not text:
        raise CommandError(f'{table} is missing a value.')
    if text.upper() == 'NULL':
        return None
    if text[0].isdigit() or (text[0] == '-' and len(text) > 1 and text[1].isdigit()):
        if any(mark in text for mark in ('.', 'e', 'E')):
            return Decimal(text)
        return int(text)
    raise CommandError(f'Cannot read SQL value {text!r} in {table}.')


def _skip_statement(chars):
    """Drop the rest of a statement, including semicolons that sit inside strings."""
    while True:
        char = chars.peek(1)
        if not char:
            return
        if char == "'":
            chars.get()
            _skip_string(chars)
            continue
        chars.get()
        if char == ';':
            return


def _skip_string(chars):
    while True:
        char = chars.get()
        if char == '\\':
            chars.get()
            continue
        if char == "'":
            if chars.peek(1) == "'":
                chars.get()
                continue
            return
