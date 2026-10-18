from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool


class ScriptedModel(GenericFakeChatModel):
    """Modelo falso que responde com mensagens roteirizadas e aceita bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self


def scripted(*messages):
    return ScriptedModel(messages=iter(messages))


def tool_call(name, args, id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def make_tool(name, calls=None):
    @tool(name)
    def _t(x: str = "") -> str:
        """tool falsa"""
        if calls is not None:
            calls.append(name)
        return f"{name}-ok"

    return _t
