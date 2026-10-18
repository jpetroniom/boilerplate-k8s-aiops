import logging

import pytest
from fakes import make_tool, scripted, tool_call
from langchain_core.messages import AIMessage

from my_agent_app.agents import analysis as a


@pytest.mark.parametrize("raw,expected", [("10", 10), ("abc", 25), ("0", 25), ("-3", 25), ("2.5", 25)])
def test_max_iterations(monkeypatch, raw, expected):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", raw)
    assert a.get_max_iterations() == expected


def test_defaults(monkeypatch):
    for n in ("AGENT_MAX_ITERATIONS", "ANALYSIS_STALE_TIMEOUT_MINUTES", "AGENT_MODEL_NAME", "MCP_SERVER_URL"):
        monkeypatch.delenv(n, raising=False)
    assert a.get_max_iterations() == 25
    assert a.get_stale_timeout_minutes() == 30
    assert a.get_model_name() == "claude-haiku-4-5"
    assert a.get_mcp_server_url() == "http://localhost:3001/mcp"


def test_invalid_values_warn(monkeypatch, caplog):
    monkeypatch.setenv("ANALYSIS_STALE_TIMEOUT_MINUTES", "x")
    with caplog.at_level(logging.WARNING):
        assert a.get_stale_timeout_minutes() == 30
    assert "ANALYSIS_STALE_TIMEOUT_MINUTES" in caplog.text


def test_model_name_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_NAME", "claude-sonnet-5-5")
    assert a.get_model_name() == "claude-sonnet-5-5"


def test_select_read_tools_drops_write_tools():
    names = ["kubectl_get", "kubectl_describe", "kubectl_logs", "kubectl_apply", "kubectl_patch", "kubectl_delete"]
    selected = a.select_read_tools([make_tool(n) for n in names])
    assert [t.name for t in selected] == ["kubectl_get", "kubectl_describe", "kubectl_logs"]


def test_missing_read_tool_aborts():
    with pytest.raises(a.AnalysisAborted):
        a.select_read_tools([make_tool("kubectl_get")])


class FailingClient:
    async def get_tools(self):
        raise ConnectionError("down")


async def test_mcp_unavailable_aborts():
    with pytest.raises(a.AnalysisAborted):
        await a.load_read_tools(FailingClient())


def read_tools(calls=None):
    return [make_tool(n, calls) for n in a.READ_TOOLS]


async def test_agent_runs_a_tool_then_answers():
    calls = []
    model = scripted(tool_call("kubectl_describe", {"x": "pod"}), AIMessage(content="## Problema 1: x"))
    out = await a.analyze([{"uid": "u1"}], model=model, tools=read_tools(calls))
    assert calls == ["kubectl_describe"] and out == "## Problema 1: x"


async def test_iteration_limit_ends_gracefully(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "2")
    calls = []
    model = scripted(*[tool_call("kubectl_get", {"x": str(i)}, id=f"c{i}") for i in range(10)])
    out = await a.analyze([{"uid": "u1"}], model=model, tools=read_tools(calls))
    assert len(calls) <= 2
    assert "## Problema" not in out


def test_prompt_contains_events_and_literal_braces():
    p = a.build_prompt([{"uid": "u-123"}])
    assert "u-123" in p and '{"spec":...}' in p and "{events}" not in p
