import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

REPORT_TITLE = "# Relatorio de Diagnostico Kubernetes"
_PROBLEM_HEADER = re.compile(r"^## Problema\s+\d+\s*:?.*$", re.MULTILINE)
_FIELD = r"^[-*]\s*\*\*{name}:?\*\*:?\s*(.*)$"


@dataclass
class Problem:
    markdown: str
    event_uids: list[str]
    severity: str = ""
    namespace: str = ""
    resources: str = ""
    title: str = field(default="")


def _field(block: str, name: str) -> str:
    match = re.search(_FIELD.format(name=name), block, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _split_uids(raw: str) -> list[str]:
    return [u for u in re.split(r"[\s,;]+", raw.replace("`", "")) if u]


def parse_problems(response: str, batch_uids: list[str]) -> list[Problem]:
    """Extrai um Problem por bloco `## Problema N` da resposta do agente.

    Uids fora do lote sao ignorados; uids do lote que nenhum problema referencia geram warning.
    """
    headers = list(_PROBLEM_HEADER.finditer(response or ""))
    if not headers:
        return []
    batch = set(batch_uids)
    problems = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(response)
        block = response[header.start() : end].rstrip().rstrip("-").rstrip()
        uids = [u for u in _split_uids(_field(block, "Eventos")) if u in batch]
        problems.append(
            Problem(
                markdown=f"{REPORT_TITLE}\n\n{block}\n",
                event_uids=list(dict.fromkeys(uids)),
                severity=_field(block, "Severidade").upper(),
                namespace=_field(block, "Namespace"),
                resources=_field(block, "Recursos Afetados"),
                title=header.group(0).lstrip("# ").strip(),
            )
        )
    referenced = {u for p in problems for u in p.event_uids}
    missing = batch - referenced
    if missing:
        logger.warning("Eventos sem relatorio proprio (nao referenciados em nenhum problema): %s", sorted(missing))
    return problems
