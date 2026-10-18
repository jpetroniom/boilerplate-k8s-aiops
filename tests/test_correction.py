import asyncio
import logging

import pytest
from fakes import make_tool, scripted, tool_call
from langchain_core.messages import AIMessage
from sqlalchemy import select

from my_agent_app.agents import correction as c
from my_agent_app.models import Report, ReportStatus


@pytest.mark.parametrize("raw,expected", [("10", 10), ("abc", 25), ("0", 25), ("-1", 25)])
def test_max_iterations(monkeypatch, raw, expected):
    monkeypatch.setenv("CORRECTION_MAX_ITERATIONS", raw)
    assert c.get_max_iterations() == expected


def test_default_and_invalid_warning(monkeypatch, caplog):
    monkeypatch.delenv("CORRECTION_MAX_ITERATIONS", raising=False)
    assert c.get_max_iterations() == 25
    monkeypatch.setenv("CORRECTION_MAX_ITERATIONS", "x")
    with caplog.at_level(logging.WARNING):
        c.get_max_iterations()
    assert "CORRECTION_MAX_ITERATIONS" in caplog.text


@pytest.mark.parametrize(
    "text,status,summary",
    [
        ("CORRIGIDO: deployment saudavel\n\n## Acoes", ReportStatus.CORRIGIDO, "deployment saudavel"),
        ("FALHA: pod continua quebrado", ReportStatus.FALHA_CORRECAO, "pod continua quebrado"),
        ("Fiz varias coisas.\n\nCORRIGIDO: ok", ReportStatus.CORRIGIDO, "ok"),
        ("- FALHA: x", ReportStatus.FALHA_CORRECAO, "x"),
        ("**texto**\n> CORRIGIDO: y", ReportStatus.CORRIGIDO, "y"),
        ("## CORRIGIDO: z", ReportStatus.CORRIGIDO, "z"),
        ("FALHA: primeiro\nCORRIGIDO: segundo", ReportStatus.FALHA_CORRECAO, "primeiro"),
    ],
)
def test_parse_verdict(text, status, summary):
    assert c.parse_verdict(text) == (status, summary)


def test_verdict_mid_sentence_is_not_a_verdict(caplog):
    with caplog.at_level(logging.WARNING):
        assert c.parse_verdict("Tudo certo, entao CORRIGIDO: sim")[0] == ReportStatus.FALHA_CORRECAO
    assert "sem veredito" in caplog.text


def test_no_verdict_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert c.parse_verdict("")[0] == ReportStatus.FALHA_CORRECAO
    assert "sem veredito" in caplog.text


class FailingClient:
    async def get_tools(self):
        raise ConnectionError("down")


class Client:
    def __init__(self, tools):
        self.tools = tools

    async def get_tools(self):
        return self.tools


async def test_all_tools_kept_including_write_tools():
    names = ["kubectl_get", "kubectl_patch", "kubectl_apply", "kubectl_delete"]
    tools = await c.load_all_tools(Client([make_tool(n) for n in names]))
    assert [t.name for t in tools] == names


async def test_mcp_unavailable_aborts():
    with pytest.raises(c.CorrectionAborted):
        await c.load_all_tools(FailingClient())


async def test_report_goes_into_prompt_and_agent_calls_write_tool():
    calls = []
    tools = [make_tool("kubectl_patch", calls), make_tool("kubectl_get", calls)]
    model = scripted(tool_call("kubectl_patch", {"x": "p"}), AIMessage(content="CORRIGIDO: ok"))
    out = await c.correct("# Relatorio MARCADOR-123", model=model, tools=tools)
    assert calls == ["kubectl_patch"] and out == "CORRIGIDO: ok"
    assert "MARCADOR-123" in c.build_prompt("# Relatorio MARCADOR-123") and "{report_markdown}" not in c.build_prompt("x")


async def test_iteration_limit_ends_without_verdict(monkeypatch):
    monkeypatch.setenv("CORRECTION_MAX_ITERATIONS", "2")
    calls = []
    model = scripted(*[tool_call("kubectl_get", {"x": str(i)}, id=f"c{i}") for i in range(10)])
    out = await c.correct("r", model=model, tools=[make_tool("kubectl_get", calls)])
    assert len(calls) <= 2
    assert c.parse_verdict(out)[0] == ReportStatus.FALHA_CORRECAO


async def add_corrigindo(sm, md="# r"):
    async with sm() as s:
        r = Report(markdown=md, status=ReportStatus.CORRIGINDO, event_uids=["u"])
        s.add(r)
        await s.commit()
        return r.id


async def load(sm, rid):
    async with sm() as s:
        return (await s.execute(select(Report).where(Report.id == rid))).scalar_one()


@pytest.mark.parametrize(
    "response,status",
    [
        ("CORRIGIDO: ok\n\n## Acoes Executadas", "CORRIGIDO"),
        ("FALHA: nao resolveu", "FALHA_CORRECAO"),
        ("sem veredito aqui", "FALHA_CORRECAO"),
    ],
)
async def test_run_correction_classifies_and_stores_result(sessionmaker, response, status):
    rid = await add_corrigindo(sessionmaker)
    seen = {}

    async def fake(md):
        seen["md"] = md
        return response

    await c.run_correction(sessionmaker, rid, correct_fn=fake)
    r = await load(sessionmaker, rid)
    assert (r.status, r.correction_result) == (status, response) and seen["md"] == "# r"


@pytest.mark.parametrize("exc", [c.CorrectionAborted("mcp down"), RuntimeError("claude api")])
async def test_run_correction_infra_failure_is_falha_correcao(sessionmaker, exc):
    rid = await add_corrigindo(sessionmaker)

    async def boom(md):
        raise exc

    await c.run_correction(sessionmaker, rid, correct_fn=boom)
    r = await load(sessionmaker, rid)
    assert r.status == "FALHA_CORRECAO" and str(exc) in r.correction_result


async def test_run_correction_does_not_overwrite_recovered_report(sessionmaker):
    rid = await add_corrigindo(sessionmaker)

    async def fake(md):
        async with sessionmaker() as s:
            from my_agent_app.models import queries

            await queries.recover_corrections(s)
        return "CORRIGIDO: tarde demais"

    await c.run_correction(sessionmaker, rid, correct_fn=fake)
    r = await load(sessionmaker, rid)
    assert (r.status, r.correction_result) == ("FALHA_CORRECAO", None)


async def test_run_correction_never_raises(sessionmaker):
    import uuid

    await asyncio.wait_for(c.run_correction(sessionmaker, uuid.uuid4()), timeout=5)
