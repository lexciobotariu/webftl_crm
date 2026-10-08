import re

import pytest
from django.template import Context, Template
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory
from apps.tasks.factories import TaskActivityFactory, TaskFactory
from apps.tasks.templatetags.task_markdown import render_markdown


class TestRenderMarkdown:
    def test_the_basics_render(self):
        html = render_markdown('**bold** and _em_ and `code`\n\n- one\n- two\n\n```\nblock\n```')

        assert '<strong>bold</strong>' in html
        assert '<em>em</em>' in html
        assert '<code>code</code>' in html
        assert '<ul>' in html and '<li>one</li>' in html
        assert '<pre><code>block' in html

    def test_a_single_newline_is_kept(self):
        assert '<br>' in render_markdown('first\nsecond')

    def test_a_hash_without_a_space_is_not_a_heading(self):
        html = render_markdown('#123 is the ticket')

        assert '<h1>' not in html
        assert '#123 is the ticket' in html

    def test_links_open_in_a_new_tab_without_the_opener(self):
        html = render_markdown('[docs](https://example.com/a)')

        assert 'href="https://example.com/a"' in html
        assert 'target="_blank"' in html
        assert 'noopener' in html and 'noreferrer' in html

    def test_bare_urls_become_links(self):
        assert 'href="https://example.com"' in render_markdown('see https://example.com today')

    def test_mailto_links_are_kept(self):
        assert 'href="mailto:a@example.com"' in render_markdown('[mail](mailto:a@example.com)')

    @pytest.mark.parametrize('source', [
        '[x](javascript:alert(1))',
        '[x](JaVaScRiPt:alert(1))',
        '[x](data:text/html;base64,PHNjcmlwdD4=)',
        '[x](vbscript:msgbox(1))',
        '<a href="javascript:alert(1)">x</a>',
    ])
    def test_dangerous_link_schemes_never_become_hrefs(self, source):
        html = render_markdown(source).lower()

        # Escaped text may still spell it out; what matters is that no tag carries it.
        assert not re.search(r'<a[^>]*href="(javascript|data|vbscript)', html)

    @pytest.mark.parametrize('source', [
        '<script>alert(1)</script>',
        '<img src=x onerror=alert(1)>',
        '<iframe src="https://evil.example"></iframe>',
        '<div onclick="alert(1)">hi</div>',
        '<style>body{display:none}</style>',
    ])
    def test_raw_html_is_shown_as_text(self, source):
        html = render_markdown(source)

        assert '<script' not in html and '<img' not in html and '<iframe' not in html
        assert '<div' not in html and '<style' not in html
        assert '&lt;' in html

    def test_images_are_not_embedded(self):
        html = render_markdown('![tracker](https://evil.example/pixel.png)')

        assert '<img' not in html
        assert 'https://evil.example/pixel.png' in html

    def test_old_plain_text_reads_the_same(self):
        html = render_markdown('Call the client.\nThen send 2 * 3 quotes.')

        assert 'Call the client.<br>' in html
        assert 'Then send 2 * 3 quotes.' in html

    def test_empty_input_is_empty(self):
        assert render_markdown('') == ''
        assert render_markdown(None) == ''

    def test_the_filter_output_is_not_escaped_again(self):
        html = Template('{% load task_markdown %}{{ text|render_markdown }}').render(Context({'text': '**b**'}))

        assert '<strong>b</strong>' in html


def _member(**flags):
    preset = PermissionPreset.objects.create(
        name=f'md{PermissionPreset.objects.count()}', access_projects=True, **flags
    )
    return UserFactory(permission_preset=preset)


@pytest.mark.django_db
class TestPreview:
    def test_it_renders_markdown(self, client):
        client.force_login(AdminUserFactory())

        response = client.post(reverse('markdown_preview'), {'text': '**b** <script>x</script>'})

        assert response.status_code == 200
        content = response.content.decode()
        assert '<strong>b</strong>' in content
        assert '<script>' not in content

    def test_empty_text_says_so(self, client):
        client.force_login(AdminUserFactory())

        assert 'Nothing to preview' in client.post(reverse('markdown_preview'), {'text': '  '}).content.decode()

    def test_it_needs_a_login_and_a_post(self, client):
        assert client.post(reverse('markdown_preview'), {'text': 'x'}).status_code == 302

        # Notes and project descriptions use the editor too, so the tasks module is not needed.
        client.force_login(_member(access_tasks=False))
        assert client.post(reverse('markdown_preview'), {'text': 'x'}).status_code == 200

        client.force_login(_member(access_tasks=True))
        assert client.get(reverse('markdown_preview')).status_code == 405
        assert client.post(reverse('markdown_preview'), {'text': 'x'}).status_code == 200

    def test_very_long_text_is_refused(self, client):
        client.force_login(AdminUserFactory())

        assert client.post(reverse('markdown_preview'), {'text': 'x' * 100_001}).status_code == 400


@pytest.mark.django_db
class TestWhereItRenders:
    def test_the_description_renders_markdown(self, client):
        admin = AdminUserFactory()
        task = TaskFactory(description='**bold** [link](https://example.com)')
        client.force_login(admin)

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        assert '<strong>bold</strong>' in html
        assert 'class="markdown' in html

    def test_a_click_on_a_link_in_the_description_does_not_start_editing(self, client):
        admin = AdminUserFactory()
        task = TaskFactory(description='[link](https://example.com)')
        client.force_login(admin)

        html = client.get(reverse('task_edit_description', args=[task.pk]) + '?cancel=1').content.decode()

        assert "click[!event.target.closest('a')]" in html
        assert 'aria-label="Edit description"' in html

    def test_a_comment_renders_markdown_and_escapes_html(self, client):
        admin = AdminUserFactory()
        task = TaskFactory()
        TaskActivityFactory(task=task, user=admin, content='**done** <b onclick=x>raw</b>')
        client.force_login(admin)

        html = client.get(reverse('task_activity_list', args=[task.pk])).content.decode()

        assert '<strong>done</strong>' in html
        assert '&lt;b onclick=x&gt;raw&lt;/b&gt;' in html

    def test_the_description_editor_and_comment_box_have_write_and_preview_tabs(self, client):
        admin = AdminUserFactory()
        task = TaskFactory()
        ProjectAccessFactory(project=task.project, user=admin)
        client.force_login(admin)

        drawer = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        editor = client.get(reverse('task_edit_description', args=[task.pk])).content.decode()

        for html in (drawer, editor):
            assert 'role="tablist"' in html
            assert '>Write</button>' in html and '>Preview</button>' in html
            assert reverse('markdown_preview') in html


class TestReviewFixes:
    def test_a_scheme_only_the_sanitizer_stops_has_no_href(self):
        # markdown-it lets data:image through; nh3's scheme list must drop it.
        html = render_markdown('[x](data:image/png;base64,AAAA)')

        assert 'data:image' not in html

    def test_text_over_the_limit_is_shown_escaped_without_parsing(self):
        from apps.tasks.templatetags.task_markdown import MAX_LENGTH

        text = '**not bold** <b>x</b>\n' + 'a' * MAX_LENGTH
        html = render_markdown(text)

        assert '<strong>' not in html
        assert '&lt;b&gt;x&lt;/b&gt;' in html
        assert '<br>' in html or '<p>' in html


@pytest.mark.django_db
class TestLengthLimitsOnSave:
    def test_a_too_long_description_is_refused(self, client):
        from apps.tasks.templatetags.task_markdown import MAX_LENGTH

        task = TaskFactory(description='keep')
        client.force_login(AdminUserFactory())

        response = client.post(reverse('task_edit_description', args=[task.pk]), {'description': 'x' * (MAX_LENGTH + 1)})

        assert response.status_code == 400
        task.refresh_from_db()
        assert task.description == 'keep'

    def test_a_too_long_comment_is_refused(self, client):
        from apps.tasks.templatetags.task_markdown import MAX_LENGTH

        task = TaskFactory()
        client.force_login(AdminUserFactory())

        response = client.post(reverse('comment_create', args=[task.pk]), {'content': 'x' * (MAX_LENGTH + 1)})

        assert response.status_code == 400
        assert not task.activities.filter(activity_type='comment').exists()

    def test_the_task_form_refuses_a_too_long_description(self):
        from apps.tasks.forms import TaskForm
        from apps.tasks.templatetags.task_markdown import MAX_LENGTH

        task = TaskFactory()
        form = TaskForm(task.project, data={'title': 'T', 'description': 'x' * (MAX_LENGTH + 1)})

        assert not form.is_valid()
        assert 'description' in form.errors

    def test_the_comment_form_drops_a_second_submit_while_one_is_in_flight(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        assert 'hx-sync="this:drop"' in html

    def test_escape_in_the_description_editor_is_handled_on_the_form(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())

        html = client.get(reverse('task_edit_description', args=[task.pk])).content.decode()

        # One handler on the form covers the textarea and the tab buttons, and it
        # leaves an Escape the Preview tab already handled alone.
        assert '@keydown.escape="cancel($event)"' in html
        assert "addEventListener('keydown'" not in html


class TestLinks:
    def test_a_file_name_is_not_a_link(self):
        html = render_markdown('edit manage.py and README.md then run deploy.sh')

        assert '<a ' not in html
        assert 'manage.py' in html and 'README.md' in html

    def test_a_url_and_an_email_address_still_are(self):
        html = render_markdown('see https://example.com/a or write to a@b.co')

        assert 'href="https://example.com/a"' in html
        assert 'href="mailto:a@b.co"' in html
