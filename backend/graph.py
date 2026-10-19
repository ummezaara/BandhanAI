"""
LangGraph workflow definitions for BandhanAI.

This module defines the agentic state machine that powers Ralph:
  - assistant_node: Invokes the LLM with system prompt + conversation history
  - human_tool_review_node: Human-in-the-loop interrupt for protected tools
  - tools (ToolNode): Executes MCP tool calls

The graph supports:
  - Per-tenant MCP configs (via mcp_config_override)
  - Per-tenant system prompts (via system_prompt)
  - Persistent checkpointing via AsyncPostgresSaver (or MemorySaver fallback)
"""

from typing import Annotated, List, Literal, TypedDict
from langchain_groq import ChatGroq
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    AIMessage,
    ToolMessage
)
from langgraph.types import Command, interrupt
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient
import json
from langchain_core.tools import StructuredTool, tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from backend.app.agents.analytics_chat.sql_guard import validate_query

_pg_pool = None

def set_pg_pool(pool):
    """Inject connection pool into memory tools."""
    global _pg_pool
    _pg_pool = pool

@tool
async def save_agent_memory(
    content: str,
    memory_type: str = "fact",
    scope: str = "tenant",
    importance: int | str = 5,
    config: Annotated[RunnableConfig, InjectedToolArg()] = None,
) -> str:
    """Save a piece of memory/knowledge about the user, business, customer behavior, or past decisions.
    Use this to remember facts, user preferences, tones, or strategy learnings.
    
    Args:
        content: The fact, preference, or learning to remember.
        memory_type: One of 'preference', 'fact', 'strategy', 'decision', 'campaign_learning', 'schema_learning'.
        scope: One of 'tenant', 'user', 'agent'.
        importance: Rating from 1 (low) to 10 (high) importance (accepts number or string integer).
    """
    if not _pg_pool:
        return "Database pool not initialized"

    try:
        importance_val = int(importance)
    except (TypeError, ValueError):
        importance_val = 5

    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id", "")
    org_id = thread_id.split(":", 1)[0] if ":" in thread_id else thread_id
    if not org_id:
        return "Could not determine organization ID from config"

    try:
        async with _pg_pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO public.agent_memories (org_id, scope, memory_type, content, importance)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (org_id, scope, memory_type, content, importance_val)
            )
        return f"Memory successfully saved: {content}"
    except Exception as e:
        return f"Failed to save memory: {e}"

@tool
async def recall_agent_memories(
    memory_type: str = None,
    config: Annotated[RunnableConfig, InjectedToolArg()] = None,
) -> str:
    """Retrieve saved memories/facts about the user, business, or database structure.
    
    Args:
        memory_type: Optional filter (e.g. 'preference', 'fact', 'schema_learning').
    """
    if not _pg_pool:
        return "Database pool not initialized"

    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id", "")
    org_id = thread_id.split(":", 1)[0] if ":" in thread_id else thread_id
    if not org_id:
        return "Could not determine organization ID from config"

    try:
        async with _pg_pool.connection() as conn:
            if memory_type:
                res = await conn.execute(
                    """
                    SELECT memory_type, content, importance
                    FROM public.agent_memories
                    WHERE org_id = %s AND memory_type = %s
                    ORDER BY importance DESC, created_at DESC
                    LIMIT 15
                    """,
                    (org_id, memory_type)
                )
            else:
                res = await conn.execute(
                    """
                    SELECT memory_type, content, importance
                    FROM public.agent_memories
                    WHERE org_id = %s
                    ORDER BY importance DESC, created_at DESC
                    LIMIT 20
                    """,
                    (org_id,)
                )
            rows = await res.fetchall()
            if not rows:
                return "No memories found."
            
            lines = []
            for r in rows:
                lines.append(f"- [{r['memory_type'].upper()}] {r['content']} (importance: {r['importance']})")
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to recall memories: {e}"


class AgentState(TypedDict):
    """The state of the agent.
    
    Attributes:
        messages: The list of messages in the conversation.
        protected_tools: Tool names that require human approval before execution.
        yolo_mode: Whether to skip human review of protected tool calls.
    """
    messages: Annotated[List[BaseMessage], add_messages]
    protected_tools: List[str]
    yolo_mode: bool


async def create_mcp_client(mcp_config_override: dict = None):
    """
    Create a MultiServerMCPClient and load tools.
    
    Returns:
        tuple: (client, tools) — the MCP client and the list of tools.
    """
    if mcp_config_override:
        active_mcp_config = mcp_config_override
    else:
        from backend.config import mcp_config
        active_mcp_config = mcp_config

    servers = active_mcp_config.get("mcpServers", {})
    client = MultiServerMCPClient(servers)
    tools = await client.get_tools()
    return client, tools


def _extract_sql_arg_name(tool_obj) -> str:
    """Best-effort detection of the MCP postgres query argument name."""
    try:
        args = getattr(tool_obj, "args", None) or {}
        if "sql" in args:
            return "sql"
        if "query" in args:
            return "query"
        if len(args) == 1:
            return next(iter(args))
    except Exception:
        pass
    return "query"


def _wrap_execute_sql_tool(source_tool):
    """Add SQL safety validation in front of the tenant database query tool."""
    sql_arg_name = _extract_sql_arg_name(source_tool)

    async def guarded_execute_sql(sql: str) -> str:
        """Run a read-only SQL SELECT query against the tenant database."""
        is_safe, error = validate_query(sql)
        if not is_safe:
            return f"SQL blocked by safety guard: {error}"

        payload = {sql_arg_name: sql}
        try:
            return await source_tool.ainvoke(payload)
        except TypeError:
            return await source_tool.ainvoke(sql)

    return StructuredTool.from_function(
        coroutine=guarded_execute_sql,
        name="execute_sql",
        description=(
            "Run one read-only SQL SELECT query against the tenant's connected "
            "Postgres database. The query is validated before execution."
        ),
    )


def prepare_agent_tools(tools: list) -> list:
    """Normalize MCP tools and attach BandhanAI built-in tools."""
    cleaned_tools = []
    for t in tools:
        # If it is a database tool, keep only 'query' and rename it to 'execute_sql'
        if "tenant_customers" in t.name:
            if not (t.name.endswith("query") or t.name.endswith("postgres_query")):
                continue
            cleaned_tools.append(_wrap_execute_sql_tool(t))
            continue

        name_clean = t.name.replace("__", "_")
        if name_clean.startswith("marketing_"):
            name_clean = name_clean.replace("marketing_", "", 1)
        if name_clean.startswith("pd_"):
            name_clean = name_clean.replace("pd_", "", 1)
        if name_clean.startswith("tenant_customers_"):
            name_clean = name_clean.replace("tenant_customers_", "", 1)

        if name_clean == "query" or name_clean == "postgres_query":
            cleaned_tools.append(_wrap_execute_sql_tool(t))
            continue

        t.name = name_clean
        cleaned_tools.append(t)

    return cleaned_tools + [save_agent_memory, recall_agent_memories]


async def build_graph(
    checkpointer=None,
    mcp_config_override: dict = None,
    system_prompt: str = None,
    tools=None,
):
    """
    Build the LangGraph application.
    
    Args:
        checkpointer: LangGraph checkpointer instance (AsyncPostgresSaver for production,
                       MemorySaver fallback for dev/CLI). Defaults to MemorySaver if None.
        mcp_config_override: Per-tenant MCP config dict. If None, falls back to the
                              static mcp_config from config.py. Ignored if tools is provided.
        system_prompt: Per-tenant system prompt string. If None, falls back to the
                        default ralph_system_prompt.
        tools: Pre-loaded list of tools. If provided, skips MCP client creation.
    
    Returns:
        Compiled LangGraph StateGraph ready for streaming.
    """
    # Resolve system prompt
    if system_prompt is None:
        from backend.prompts import ralph_system_prompt
        active_prompt = ralph_system_prompt
    else:
        active_prompt = system_prompt

    # If tools not provided, create MCP client inline (for CLI usage)
    _inline_client = None
    if tools is None:
        _inline_client, tools = await create_mcp_client(mcp_config_override)

    tools = prepare_agent_tools(tools)

    # Initialize LLM with tools
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1
    ).bind_tools(tools)

    # Create a fallback LLM without tools for when tool calling fails
    llm_no_tools = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )

    async def assistant_node(state: AgentState, config: RunnableConfig = None):
        """Invoke the LLM with the system prompt and conversation history."""
        # Query memories dynamically at runtime
        memories_ctx = ""
        configurable = config.get("configurable", {}) if config else {}
        thread_id = configurable.get("thread_id", "")
        org_id = thread_id.split(":", 1)[0] if ":" in thread_id else thread_id

        if org_id and _pg_pool:
            try:
                async with _pg_pool.connection() as conn:
                    res = await conn.execute(
                        """
                        SELECT memory_type, content
                        FROM public.agent_memories
                        WHERE org_id = %s
                        ORDER BY importance DESC, created_at DESC
                        LIMIT 15
                        """,
                        (org_id,)
                    )
                    rows = await res.fetchall()
                    if rows:
                        lines = [
                            "\n<SAVED_MEMORIES_AND_FACTS>",
                            "Here is what you have remembered about this business, user preferences, and strategies:",
                        ]
                        for r in rows:
                            lines.append(f"- [{r['memory_type'].upper()}] {r['content']}")
                        lines.append("</SAVED_MEMORIES_AND_FACTS>")
                        memories_ctx = "\n".join(lines)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(f"Error loading memories dynamically: {exc}")

        # Construct final dynamic prompt
        dynamic_prompt = active_prompt
        if memories_ctx:
            dynamic_prompt += "\n" + memories_ctx

        full_messages = [SystemMessage(content=dynamic_prompt)] + state["messages"]

        # Check if the last message was a failed ToolMessage
        last_msg = state["messages"][-1] if state["messages"] else None
        if isinstance(last_msg, ToolMessage):
            content_lower = str(last_msg.content).lower()
            if "does not exist" in content_lower or "error" in content_lower or "blocked by safety guard" in content_lower:
                retry_directive = SystemMessage(
                    content=(
                        f"CRITICAL DIRECTIVE: The database query failed with error: '{last_msg.content}'.\n"
                        "NEVER output this raw SQL error string to the user!\n"
                        "If you can fix the query using table JOINs or correct column names from the schema context above, call execute_sql with the corrected query.\n"
                        "Otherwise, summarize politely in friendly English what information is available in the database."
                    )
                )
                full_messages.append(retry_directive)
        
        try:
            response = await llm.ainvoke(full_messages)
            return {"messages": [response]}
        except Exception as e:
            error_msg = str(e)
            # Groq sometimes fails tool calls with certain prompts — retry without tools
            if "Failed to call a function" in error_msg or "failed_generation" in error_msg:
                import logging
                logging.getLogger(__name__).warning(
                    f"Tool call failed, retrying without tools: {error_msg}"
                )
                # Ask the LLM to respond in plain text
                retry_messages = full_messages + [
                    SystemMessage(
                        content="Your previous attempt to call a tool failed. "
                        "Please respond to the user's question in plain text. "
                        "If you need to query the database, describe what query you would run "
                        "and I will help you execute it on the next turn."
                    )
                ]
                response = await llm_no_tools.ainvoke(retry_messages)
                return {"messages": [response]}
            else:
                raise
    
    async def human_tool_review_node(state: AgentState) -> Command[Literal["assistant_node", "tools"]]:
        """
        Human-in-the-loop review node.
        
        Interrupts execution and waits for user to:
          - 'continue': Approve and execute the tool call as-is
          - 'update': Modify the tool call arguments before execution
          - 'feedback': Reject with a reason, sent back to the LLM
        """
        last_message = state["messages"][-1]
        tool_call = last_message.tool_calls[-1]

        human_review: dict = interrupt({
            "message": "Your input is required for the following tool:",
            "tool_call": tool_call
        })

        review_action = human_review["action"]
        review_data = human_review.get("data")

        if review_action == "continue":
            return Command(goto="tools")
        
        elif review_action == "update":
            updated_message = AIMessage(
                content=last_message.content,
                tool_calls=[{
                    "id": tool_call["id"],
                    "name": tool_call["name"],
                    "args": json.loads(review_data)
                }],
                id=last_message.id
            )
            return Command(goto="tools", update={"messages": [updated_message]})
        
        elif review_action == "feedback":
            tool_message = ToolMessage(
                content=review_data,
                name=tool_call["name"],
                tool_call_id=tool_call["id"]
            )
            return Command(goto="assistant_node", update={"messages": [tool_message]})

    # --- Routing Logic ---

    async def assistant_router(state: AgentState) -> str:
        """Route after assistant response: END if no tool calls, else tools or review."""
        last_message = state["messages"][-1]
        if not last_message.tool_calls:
            return END
        else:
            if not state.get("yolo_mode", False):
                protected = state.get("protected_tools", [
                    "create_campaign", 
                    "send_campaign_email", 
                    "marketing_create_campaign", 
                    "marketing_send_campaign_email"
                ])
                if any(
                    tool_call["name"] in protected
                    for tool_call in last_message.tool_calls
                ):
                    return "human_tool_review_node"
            return "tools"

    # --- Build Graph ---

    builder = StateGraph(AgentState)

    builder.add_node(assistant_node)
    builder.add_node(human_tool_review_node)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "assistant_node")
    builder.add_conditional_edges(
        "assistant_node",
        assistant_router,
        ["tools", "human_tool_review_node", END],
    )
    builder.add_edge("tools", "assistant_node")

    # Use provided checkpointer or fall back to in-memory
    if checkpointer is None:
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Graph Visualization Utilities (CLI only)
# ---------------------------------------------------------------------------

def inspect_graph_cli(graph, output_file="graph.png"):
    """Visualize the graph and save as PNG file for CLI usage."""
    try:
        png_data = graph.get_graph(xray=True).draw_mermaid_png()
        with open(output_file, "wb") as f:
            f.write(png_data)
        
        print(f"Graph visualization saved to {output_file}")
        
        import subprocess
        import sys
        
        try:
            if sys.platform.startswith('darwin'):
                subprocess.run(['open', output_file])
            elif sys.platform.startswith('win'):
                subprocess.run(['start', output_file], shell=True)
            elif sys.platform.startswith('linux'):
                subprocess.run(['xdg-open', output_file])
            print(f"Opened {output_file} with system default viewer")
        except Exception as e:
            print(f"Could not auto-open file: {e}")
            
    except Exception as e:
        print(f"Error generating graph visualization: {e}")


def inspect_graph_text(graph):
    """Print a text representation of the graph structure."""
    print("=== Graph Structure ===")
    print("Nodes:", list(graph.get_graph().nodes()))
    print("Edges:", list(graph.get_graph().edges()))
    
    try:
        graph_dict = graph.get_graph(xray=True).to_dict()
        print("\n=== Detailed Graph Info ===")
        for key, value in graph_dict.items():
            if key != 'edges':
                print(f"{key}: {value}")
    except Exception as e:
        print(f"Could not get detailed graph info: {e}")


if __name__ == "__main__":
    import asyncio
    import nest_asyncio
    nest_asyncio.apply()

    graph = asyncio.run(build_graph())
    inspect_graph_cli(graph)
    inspect_graph_text(graph)
