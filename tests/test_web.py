import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from my_agent_app.main import app
from my_agent_app.models import Report, ReportStatus
from my_agent_app.web.router import render_report_detail

BODY = "# Relatorio\n\n## Problema 1: x\n- **Severidade:** {sev}\n- **Namespace:** default\n\n### Causa Raiz\n| a | b |\n|---|---|\n| 1 | 2 |\n"


async def add(sm, status, sev="ALTO", md=None, age=0):
    async with sm() as s:
        r = Report(markdown=BODY.format(sev=sev) if md is None else md, status=status, event_uids=["u"])
        s.add(r)
        await s.commit()
        if age:
            await s.execute(update(Report).where(Report.id == r.id).values(created_at=datetime.now(UTC) - timedelta(minutes=age)))
            await s.commit()
        return r.id


@pytest.fixture
async def client(sessionmaker):
    app.state.sessionmaker = sessionmaker
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_header_link_on_every_page(client):
    for path in ("/", "/reports"):
        assert 'href="/reports">Relatórios</a>' in (await client.get(path)).text


async def test_list_empty(client):
    r = await client.get("/reports")
    assert r.status_code == 200 and "Nenhum relatório encontrado" in r.text


async def test_list_order_badges_severity_and_links(sessionmaker, client):
    old = await add(sessionmaker, "COMPLETO", "CRITICO", age=60)
    new = await add(sessionmaker, "INCOMPLETO", md="", age=0)
    r = await client.get("/reports")
    assert r.text.index(str(new)) < r.text.index(str(old))
    assert f'href="/reports/{old}"' in r.text
    assert "badge-complete" in r.text and "badge-incomplete" in r.text
    assert "CRITICO" in r.text and "severity-none" in r.text


@pytest.mark.parametrize(
    "status,badge",
    [
        ("EM_ANALISE", "badge-processing"),
        ("COMPLETO", "badge-complete"),
        ("INCOMPLETO", "badge-incomplete"),
        ("CORRIGINDO", "badge-executing"),
        ("CORRIGIDO", "badge-executed"),
        ("FALHA_CORRECAO", "badge-execution-failed"),
    ],
)
async def test_badge_mapping_and_fix_button(sessionmaker, client, status, badge):
    rid = await add(sessionmaker, status)
    r = await client.get(f"/reports/{rid}")
    assert r.status_code == 200
    assert f'badge {badge}"' in r.text
    assert ("Executar correção" in r.text) == (status in ("COMPLETO", "FALHA_CORRECAO"))
    if status in ("COMPLETO", "FALHA_CORRECAO"):
        assert f'action="/reports/{rid}/fix"' in r.text and 'method="post"' in r.text


async def test_detail_renders_markdown(sessionmaker, client):
    rid = await add(sessionmaker, "COMPLETO")
    text = (await client.get(f"/reports/{rid}")).text
    assert "<table>" in text and "<h2>Problema 1: x</h2>" in text


async def test_detail_sanitizes_script(sessionmaker, client):
    rid = await add(sessionmaker, "COMPLETO", md="<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>")
    text = (await client.get(f"/reports/{rid}")).text.lower()
    assert "<script>alert" not in text and "onerror" not in text


async def test_detail_not_found_is_404(client):
    r = await client.get(f"/reports/{uuid.uuid4()}")
    assert r.status_code == 404 and "Relatório não encontrado" in r.text


async def test_non_uuid_is_422(client):
    assert (await client.get("/reports/abc")).status_code == 422


async def test_render_detail_with_conflict_message(sessionmaker):
    from starlette.requests import Request

    rid = await add(sessionmaker, "CORRIGINDO")
    request = Request({"type": "http", "method": "POST", "path": f"/reports/{rid}/fix", "headers": [], "query_string": b"", "app": app})
    async with sessionmaker() as s:
        resp = await render_report_detail(request, s, rid, message="Correção já em andamento", status_code=409)
    assert resp.status_code == 409 and "Correção já em andamento" in resp.body.decode()


class BrokenSession:
    async def execute(self, *a, **k):
        raise OperationalError("select", {}, ConnectionError("down"))

    async def get(self, *a, **k):
        raise OperationalError("get", {}, ConnectionError("down"))


class BrokenMaker:
    def __call__(self):
        return self

    async def __aenter__(self):
        return BrokenSession()

    async def __aexit__(self, *a):
        return False


@pytest.mark.parametrize("path", ["/reports", f"/reports/{uuid.uuid4()}"])
async def test_database_down_is_503(path):
    app.state.sessionmaker = BrokenMaker()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(path)
    assert r.status_code == 503
    assert "Banco de dados indisponível, tente novamente em instantes" in r.text


# --- POST /reports/{id}/fix ---


@pytest.fixture
def fixer(monkeypatch, sessionmaker):
    """Troca a correcao real por uma falsa que registra as chamadas."""
    from my_agent_app.agents import correction

    calls = []

    async def fake_correct(md):
        calls.append(md)
        await asyncio.sleep(0.05)
        return "CORRIGIDO: ok"

    async def runner(sm, report_id):
        await correction.run_correction(sm, report_id, correct_fn=fake_correct)

    monkeypatch.setattr("my_agent_app.web.router.run_correction", runner)
    return calls


async def test_fix_completo_redirects_and_runs_in_background(sessionmaker, client, fixer):
    rid = await add(sessionmaker, "COMPLETO")
    r = await client.post(f"/reports/{rid}/fix", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/reports/{rid}"
    assert len(fixer) == 1
    async with sessionmaker() as s:
        row = await s.get(Report, rid)
    assert (row.status, row.correction_result) == ("CORRIGIDO", "CORRIGIDO: ok")


async def test_fix_status_is_corrigindo_before_response(sessionmaker, client, monkeypatch):
    rid = await add(sessionmaker, "COMPLETO")
    seen = {}

    async def runner(sm, report_id):
        async with sm() as s:
            seen["status"] = (await s.get(Report, report_id)).status

    monkeypatch.setattr("my_agent_app.web.router.run_correction", runner)
    await client.post(f"/reports/{rid}/fix")
    assert seen["status"] == "CORRIGINDO"


async def test_fix_after_failure_restarts(sessionmaker, client, fixer):
    rid = await add(sessionmaker, "FALHA_CORRECAO")
    assert (await client.post(f"/reports/{rid}/fix")).status_code == 303 and len(fixer) == 1


@pytest.mark.parametrize("status", ["EM_ANALISE", "INCOMPLETO", "CORRIGIDO"])
async def test_fix_invalid_status_is_409_without_running(sessionmaker, client, fixer, status):
    rid = await add(sessionmaker, status)
    r = await client.post(f"/reports/{rid}/fix")
    assert r.status_code == 409 and "não permite correção" in r.text and fixer == []


async def test_fix_while_corrigindo_shows_in_progress_message(sessionmaker, client, fixer):
    rid = await add(sessionmaker, "CORRIGINDO")
    r = await client.post(f"/reports/{rid}/fix")
    assert r.status_code == 409 and "Correção já em andamento" in r.text and fixer == []
    assert "CORRIGINDO" in r.text


async def test_fix_unknown_report_is_404(client, fixer):
    r = await client.post(f"/reports/{uuid.uuid4()}/fix")
    assert r.status_code == 404 and fixer == []


async def test_fix_concurrent_requests_only_one_runs(sessionmaker, fixer):
    app.state.sessionmaker = sessionmaker
    rid = await add(sessionmaker, "COMPLETO")

    async def post():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return (await c.post(f"/reports/{rid}/fix")).status_code

    codes = await asyncio.gather(*[post() for _ in range(6)])
    assert sorted(codes) == [303] + [409] * 5 and len(fixer) == 1


async def test_fix_database_down_is_503():
    app.state.sessionmaker = BrokenMaker()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post(f"/reports/{uuid.uuid4()}/fix")).status_code == 503


async def test_correction_result_section_only_when_present(sessionmaker, client):
    plain = await add(sessionmaker, "COMPLETO")
    fixed = await add(sessionmaker, "CORRIGIDO")
    async with sessionmaker() as s:
        row = await s.get(Report, fixed)
        row.correction_result = "CORRIGIDO: ok\n\n## Acoes Executadas\n- **Acao:** patch"
        await s.commit()
    assert "Resultado da Correção" not in (await client.get(f"/reports/{plain}")).text
    text = (await client.get(f"/reports/{fixed}")).text
    assert "Resultado da Correção" in text and "<h2>Acoes Executadas</h2>" in text and "badge-executed" in text


async def test_correction_result_is_sanitized(sessionmaker, client):
    rid = await add(sessionmaker, "FALHA_CORRECAO")
    async with sessionmaker() as s:
        row = await s.get(Report, rid)
        row.correction_result = 'FALHA: x\n\n<script>alert(1)</script><img src=x onerror="alert(2)">[a](javascript:alert(3))'
        await s.commit()
    text = (await client.get(f"/reports/{rid}")).text.lower()
    assert "<script>alert" not in text and "onerror" not in text and "javascript:" not in text
