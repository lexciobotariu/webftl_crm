"""Markdown for task descriptions and comments.

This filter is the only place user text becomes markup, so it is the trust
boundary: markdown-it runs with ``html=False`` (raw HTML is escaped, not
dropped, so nothing typed disappears) and nh3 then keeps only the tags below.
Images are not rendered, so a description cannot load a tracking pixel.
"""
import nh3
from django import template
from django.utils.html import linebreaks
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

register = template.Library()

# gfm-like: CommonMark plus tables, strikethrough and bare-URL links. "breaks"
# keeps a single newline as a line break, so text written before markdown
# reads the same.
_markdown = MarkdownIt('gfm-like', options_update={'html': False, 'breaks': True}).disable('image')

ALLOWED_TAGS = {
    'p', 'br', 'hr', 'strong', 'em', 's', 'del', 'code', 'pre', 'blockquote',
    'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
}
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
    'ol': {'start'},
}
URL_SCHEMES = {'http', 'https', 'mailto'}

# Longest description or comment that is saved, and parsed. Parsing time grows
# faster than the text, so anything longer (from before the limit) is shown as
# escaped plain text instead.
MAX_LENGTH = 100_000


def markdown_to_html(text):
    if not text:
        return ''
    if len(text) > MAX_LENGTH:
        return linebreaks(text, autoescape=True)
    return nh3.clean(
        _markdown.render(text),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel='noopener noreferrer nofollow',
        set_tag_attribute_values={'a': {'target': '_blank'}},
    )


@register.filter
def render_markdown(text):
    return mark_safe(markdown_to_html(text))
