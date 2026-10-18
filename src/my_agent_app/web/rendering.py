import re

import markdown
import nh3

SEVERITY_PATTERN = re.compile(r"\*\*Severidade:?\*\*:?\s*([A-Za-zÀ-ÿ]+)", re.IGNORECASE)

ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "code", "pre",
    "blockquote", "table", "thead", "tbody", "tr", "th", "td", "a",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
ALLOWED_SCHEMES = {"http", "https", "mailto"}

STATUS_BADGES = {
    "EM_ANALISE": "badge-processing",
    "COMPLETO": "badge-complete",
    "INCOMPLETO": "badge-incomplete",
    "CORRIGINDO": "badge-executing",
    "CORRIGIDO": "badge-executed",
    "FALHA_CORRECAO": "badge-execution-failed",
}

FIXABLE_STATUSES = {"COMPLETO", "FALHA_CORRECAO"}


def extract_severity(text: str | None) -> str | None:
    match = SEVERITY_PATTERN.search(text or "")
    return match.group(1).upper() if match else None


def render_markdown(text: str | None) -> str:
    """Markdown -> HTML sanitizado (o conteudo deriva de texto do cluster processado por um LLM)."""
    html = markdown.markdown(text or "", extensions=["tables", "fenced_code"])
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        link_rel="noopener noreferrer",
    )
