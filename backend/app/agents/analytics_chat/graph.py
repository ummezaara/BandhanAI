"""Dedicated analytics chat graph.

This graph is ready for the v3 route switch once the frontend chat stream is
changed from the legacy graph to the smaller analytics workflow.
"""

from __future__ import annotations

from typing import Annotated, Any, List, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from backend.app.agents.analytics_chat.prompts import ANALYST_PROMPT, QUERY_PLANNER_PROMPT


class AnalyticsChatState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    schema_metadata: dict[str, Any]
    tenant_context: dict[str, Any]


def _schema_context(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "No schema metadata cached."

    entity_map = metadata.get("entity_map") or {}
    column_catalog = metadata.get("column_catalog") or []
    join_paths = metadata.get("join_paths") or []

    # Group columns by table name for maximum readability
    tables: dict[str, list[str]] = {}
    for col in column_catalog:
        tname = col.get("table") or col.get("table_name") or "unknown"
        cname = col.get("column")
        dtype = col.get("data_type", "")
        if cname:
            tables.setdefault(tname, []).append(f"{cname} ({dtype})")

    lines = ["BUSINESS ENTITY MAPPINGS:"]
    for entity, tname in entity_map.items():
        lines.append(f"  • {entity}: {tname}")

    lines.append("\nTABLE CATALOG & EXACT COLUMNS:")
    for tname, cols in tables.items():
        lines.append(f"  • {tname}: {', '.join(cols)}")

    lines.append("\nAVAILABLE JOIN PATHS:")
    if join_paths:
        for jp in join_paths:
            from_tbl = jp.get("from_table")
            from_col = jp.get("from_col")
            to_tbl = jp.get("to_table")
            to_col = jp.get("to_col")
            if from_tbl and to_tbl:
                lines.append(f"  • {from_tbl}.{from_col} ──> {to_tbl}.{to_col}")
    else:
        lines.append("  • No foreign keys discovered.")

    return "\n".join(lines)


async def build_analytics_chat_graph(tools: list, checkpointer=None):
    """Build the smaller query_planner -> tools -> analyst graph."""
    llm_with_tools = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1).bind_tools(tools)
    llm_no_tools = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)

    async def query_planner(state: AnalyticsChatState):
        prompt = (
            QUERY_PLANNER_PROMPT
            + "\n\n"
            + _schema_context(state.get("schema_metadata") or {})
        )
        response = await llm_with_tools.ainvoke([SystemMessage(content=prompt)] + state["messages"])
        return {"messages": [response]}

    async def analyst(state: AnalyticsChatState):
        tenant_context = state.get("tenant_context") or {}
        schema_info = _schema_context(state.get("schema_metadata") or {})
        prompt = (
            ANALYST_PROMPT
            + f"\n\nAgent tone/context: {tenant_context}"
            + f"\n\n{schema_info}"
            + "\n\nUse the tool results already present in the conversation history."
        )
        response = await llm_no_tools.ainvoke([SystemMessage(content=prompt)] + state["messages"])
        return {"messages": [response]}

    def route_after_planner(state: AnalyticsChatState):
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return "analyst"

    builder = StateGraph(AnalyticsChatState)
    builder.add_node("query_planner", query_planner)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("analyst", analyst)

    builder.add_edge(START, "query_planner")
    builder.add_conditional_edges("query_planner", route_after_planner, ["tools", "analyst"])
    builder.add_edge("tools", "query_planner")
    builder.add_edge("analyst", END)

    return builder.compile(checkpointer=checkpointer)
