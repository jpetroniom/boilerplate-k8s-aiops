import logging

from my_agent_app.agents.report_parser import parse_problems

TWO = """# Relatorio de Diagnostico Kubernetes

## Resumo
| Total | Criticos | Altos | Medios | Baixos |
|-------|----------|-------|--------|--------|
| 2     | 1        | 0     | 1      | 0      |

---

## Problema 1: Imagem inexistente
- **Severidade:** CRITICO
- **Namespace:** default
- **Recursos Afetados:** pod/nginx-1
- **Eventos:** u1, u2

### Causa Raiz
Imagem ngin:latest nao existe.

### Solucao Recomendada
Corrigir a imagem.

### Comando Sugerido
kubectl set image deployment/nginx nginx=nginx:latest

---

## Problema 2: Probe falhando
- **Severidade:** MEDIO
- **Namespace:** kube-news
- **Recursos Afetados:** pod/kube-news
- **Eventos:** `u3`

### Causa Raiz
Probe lenta.
"""


def test_two_problems_with_fields():
    problems = parse_problems(TWO, ["u1", "u2", "u3"])
    assert len(problems) == 2
    assert problems[0].event_uids == ["u1", "u2"]
    assert (problems[0].severity, problems[0].namespace) == ("CRITICO", "default")
    assert problems[1].event_uids == ["u3"] and problems[1].severity == "MEDIO"
    assert problems[0].markdown.startswith("# Relatorio de Diagnostico Kubernetes")
    assert "Comando Sugerido" in problems[0].markdown and "Problema 2" not in problems[0].markdown


def test_empty_or_no_problem_sections():
    assert parse_problems("", ["u1"]) == []
    assert parse_problems("# Relatorio\nnada", ["u1"]) == []


def test_uid_outside_batch_is_ignored():
    problems = parse_problems(TWO, ["u1"])
    assert problems[0].event_uids == ["u1"] and problems[1].event_uids == []


def test_unreferenced_batch_uid_warns(caplog):
    with caplog.at_level(logging.WARNING):
        parse_problems(TWO, ["u1", "u2", "u3", "u9"])
    assert "u9" in caplog.text
