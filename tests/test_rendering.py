import pytest

from my_agent_app.web.rendering import extract_severity, render_markdown


@pytest.mark.parametrize(
    "text,expected",
    [
        ("- **Severidade:** ALTO\n- **Namespace:** x", "ALTO"),
        ("- **Severidade:** critico", "CRITICO"),
        ("sem campo", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_severity(text, expected):
    assert extract_severity(text) == expected


def test_preserves_legitimate_formatting():
    md = (
        "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- item\n\n```\nkubectl get pods\n```\n\n[ok](https://example.com)"
    )
    html = render_markdown(md)
    for fragment in ("<h1>", "<table>", "<td>1</td>", "<li>item</li>", "<pre>", "kubectl get pods", 'href="https://example.com"'):
        assert fragment in html


def test_removes_script_event_handlers_and_js_urls():
    md = '<script>alert(1)</script>\n\n<img src=x onerror="alert(2)">\n\n[x](javascript:alert(3))\n\n<a href="javascript:alert(4)" onclick="x()">y</a>'
    html = render_markdown(md).lower()
    assert "<script" not in html and "onerror" not in html and "onclick" not in html and "javascript:" not in html


def test_malformed_markdown_does_not_raise():
    assert "<" in render_markdown("**aberto\n| a |\n```nunca fecha\n<div>")


def test_empty_markdown():
    assert render_markdown("") == ""
