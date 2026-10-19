import sys
from pathlib import Path

# Ensure project root is in sys.path so 'backend.xyz' imports resolve everywhere
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import logging
import uuid
import os
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

# Import psycopg for AsyncConnectionPool
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

# Import checkpoint savers
from langgraph.checkpoint.memory import MemorySaver
try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    try:
        from langgraph.checkpoint.postgres import PostgresSaver as AsyncPostgresSaver
    except ImportError:
        AsyncPostgresSaver = None

# Import our backend modules (supports both root and backend working directories)
try:
    from backend.graph import build_graph, create_mcp_client, prepare_agent_tools, AgentState
    from backend.app.agents.analytics_chat.graph import build_analytics_chat_graph
    from backend.auth import get_current_user, get_ws_user, get_org_id_for_user
    from backend.config import build_mcp_config_for_tenant
    from backend.prompts import build_system_prompt
    from backend.app.connections.metadata import get_latest_schema_metadata
    import backend.oauth as oauth
    import backend.app.csv.routes as csv_routes
    import backend.app.connections.routes as connection_routes
    import backend.app.crm.routes as crm_routes
    import backend.app.billing.routes as billing_routes
    import backend.app.audit.routes as audit_routes
    import backend.app.campaigns.routes as campaign_routes
    import backend.app.loyalty.routes as loyalty_routes
except ImportError:
    from graph import build_graph, create_mcp_client, prepare_agent_tools, AgentState
    from app.agents.analytics_chat.graph import build_analytics_chat_graph
    from auth import get_current_user, get_ws_user, get_org_id_for_user
    from config import build_mcp_config_for_tenant
    from prompts import build_system_prompt
    from app.connections.metadata import get_latest_schema_metadata
    import oauth as oauth
    import app.csv.routes as csv_routes
    import app.connections.routes as connection_routes
    import app.crm.routes as crm_routes
    import app.billing.routes as billing_routes
    import app.audit.routes as audit_routes
    import app.campaigns.routes as campaign_routes
    import app.loyalty.routes as loyalty_routes

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
SUPABASE_URI = os.getenv("SUPABASE_URI", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip()
BACKEND_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
if FRONTEND_URL and FRONTEND_URL not in BACKEND_CORS_ORIGINS:
    BACKEND_CORS_ORIGINS.append(FRONTEND_URL)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


YOLO_MODE_DEFAULT = _env_bool("BANDHAN_YOLO_MODE", default=False)

# Global variables for db pool and checkpointer
pool: Optional[AsyncConnectionPool] = None
checkpointer: Any = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app: handles db pool and checkpointer setup."""
    global pool, checkpointer
    if SUPABASE_URI:
        try:
            logger.info("Initializing Supabase/PostgreSQL pool...")
            pool = AsyncConnectionPool(
                conninfo=SUPABASE_URI,
                min_size=1,
                max_size=10,
                max_idle=300,
                max_lifetime=1800,
                check=AsyncConnectionPool.check_connection,
                open=True,
                kwargs={"row_factory": dict_row, "prepare_threshold": None, "autocommit": True}
            )
            # Inject connection pool into OAuth, CSV upload, and CSV pipeline modules
            oauth.set_pg_pool(pool)
            csv_routes.set_pg_pool(pool)
            connection_routes.set_pg_pool(pool)
            crm_routes.set_pg_pool(pool)
            billing_routes.set_pg_pool(pool)
            audit_routes.set_pg_pool(pool)
            campaign_routes.set_pg_pool(pool)
            loyalty_routes.set_pg_pool(pool)
            try:
                from backend.app.integrations.gmail import set_pg_pool as gmail_set_pool
                from backend.graph import set_pg_pool as graph_set_pool
            except ImportError:
                from app.integrations.gmail import set_pg_pool as gmail_set_pool
                from graph import set_pg_pool as graph_set_pool
            gmail_set_pool(pool)
            graph_set_pool(pool)
            
            _chat_sessions.clear()
            if AsyncPostgresSaver:
                logger.info("Setting up PostgresSaver checkpointer...")
                checkpointer = AsyncPostgresSaver(pool)
                # Auto-create necessary checkpointer tables
                await checkpointer.setup()
                logger.info("Postgres checkpointer setup complete.")
            else:
                logger.warning("AsyncPostgresSaver could not be imported; falling back to MemorySaver.")
                checkpointer = MemorySaver()
        except Exception as e:
            logger.error(f"Failed to initialize database pool/checkpointer: {e}")
            logger.warning("Falling back to MemorySaver for local dev.")
            checkpointer = MemorySaver()
    else:
        logger.warning("SUPABASE_URI is not set; checkpointer falling back to MemorySaver.")
        checkpointer = MemorySaver()

    yield

    if pool:
        logger.info("Closing database pool...")
        await pool.close()
        logger.info("Database pool closed.")

app = FastAPI(
    title="Bandhan AI Multi-Tenant API",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(oauth.router)
app.include_router(csv_routes.router)
app.include_router(connection_routes.router)
app.include_router(crm_routes.router)
app.include_router(billing_routes.router)
app.include_router(audit_routes.router)
app.include_router(campaign_routes.router)
app.include_router(loyalty_routes.router)

# ---------------------------------------------------------------------------
# REST Streaming Chat API (replaces WebSocket for chat)
# ---------------------------------------------------------------------------

from fastapi.responses import StreamingResponse

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

# In-memory session store for REST chat (keyed by org_id:session_id)
_chat_sessions: Dict[str, Dict[str, Any]] = {}

async def _get_approved_customer_mapping(org_id: str) -> Optional[dict]:
    """Fetch the latest approved external customer mapping for prompt context."""
    if not pool:
        return None
    async with pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT schema_name, table_name, field_map
            FROM crm_customer_mappings
            WHERE org_id = %s AND status = 'approved'
            ORDER BY approved_at DESC NULLS LAST, updated_at DESC
            LIMIT 1
            """,
            (org_id,),
        )
        row = await result.fetchone()
    return dict(row) if row else None


async def _get_latest_schema_metadata(org_id: str) -> Optional[dict]:
    """Fetch latest cached multi-table schema metadata for prompt context."""
    if not pool:
        return None
    try:
        return await get_latest_schema_metadata(pool, org_id)
    except Exception as exc:
        logger.info("Schema metadata cache unavailable for org_id=%s: %s", org_id, exc)
        return None

async def _get_or_create_session(org_id: str, session_id: str, tenant: dict) -> Dict[str, Any]:
    """Get an existing chat session or create a new one with MCP tools + graph."""
    key = f"{org_id}:{session_id}"
    if key in _chat_sessions:
        return _chat_sessions[key]

    logger.info(f"Creating new chat session: {key}")
    mcp_config = await build_mcp_config_for_tenant(org_id, pool)
    customer_mapping = await _get_approved_customer_mapping(org_id)
    schema_metadata = await _get_latest_schema_metadata(org_id)
    system_prompt = build_system_prompt(tenant, customer_mapping, schema_metadata) if tenant else None

    client, tools = await create_mcp_client(mcp_config)
    graph_type = "legacy"
    if schema_metadata:
        analytics_tools = [
            tool
            for tool in prepare_agent_tools(tools)
            if tool.name in {"execute_sql", "save_agent_memory", "recall_agent_memories"}
        ]
        graph = await build_analytics_chat_graph(
            tools=analytics_tools,
            checkpointer=checkpointer,
        )
        graph_type = "analytics"
    else:
        graph = await build_graph(
            checkpointer=checkpointer,
            system_prompt=system_prompt,
            tools=tools,
        )

    session = {
        "graph": graph,
        "config": {"configurable": {"thread_id": key}, "recursion_limit": 100},
        "mcp_client": client,
        "yolo_mode": YOLO_MODE_DEFAULT,
        "graph_type": graph_type,
        "schema_metadata": schema_metadata,
        "tenant_context": {
            "agent_name": tenant.get("agent_name") if tenant else "Ralph",
            "org_name": tenant.get("org_name") if tenant else "BandhanAI",
            "backstory": tenant.get("backstory") if tenant else "",
            "tone_instructions": tenant.get("tone_instructions") if tenant else "",
        },
    }
    _chat_sessions[key] = session
    return session

# ---------------------------------------------------------------------------
# Chat Sessions & Messages API
# ---------------------------------------------------------------------------

@app.get("/api/chat/sessions")
async def list_chat_sessions(user: dict = Depends(get_current_user)):
    """List all chat sessions for the authenticated user's organization."""
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                """
                SELECT session_id, title, created_at, updated_at
                FROM public.chat_sessions
                WHERE org_id = %s
                ORDER BY updated_at DESC
                """,
                (org_id,)
            )
            rows = await result.fetchall()
            return {"sessions": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"Failed to list chat sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"

@app.post("/api/chat/sessions")
async def create_chat_session(req: CreateSessionRequest, user: dict = Depends(get_current_user)):
    """Create a new chat session."""
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")
    org_id = await get_org_id_for_user(user["sub"], pool)
    auth_uid = user["sub"]
    
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                """
                INSERT INTO public.chat_sessions (org_id, user_auth_uid, title)
                VALUES (%s, %s, %s)
                RETURNING session_id, title, created_at, updated_at
                """,
                (org_id, auth_uid, req.title)
            )
            row = await result.fetchone()
            return dict(row)
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a chat session."""
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    try:
        async with pool.connection() as conn:
            # Delete messages and session
            await conn.execute(
                "DELETE FROM public.chat_sessions WHERE session_id = %s AND org_id = %s",
                (session_id, org_id)
            )
            return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to delete chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/sessions/{session_id}/messages")
async def load_session_messages(session_id: str, user: dict = Depends(get_current_user)):
    """Load messages history for a chat session."""
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    try:
        async with pool.connection() as conn:
            # Verify session belongs to organization
            s_res = await conn.execute(
                "SELECT session_id FROM public.chat_sessions WHERE session_id = %s AND org_id = %s",
                (session_id, org_id)
            )
            s_row = await s_res.fetchone()
            if not s_row:
                raise HTTPException(status_code=404, detail="Chat session not found")
                
            result = await conn.execute(
                """
                SELECT message_id, role, content, metadata, created_at
                FROM public.chat_messages
                WHERE session_id = %s AND org_id = %s
                ORDER BY created_at ASC
                """,
                (session_id, org_id)
            )
            rows = await result.fetchall()
            return {"messages": [dict(r) for r in rows]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# REST Streaming Chat API
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat_endpoint(
    req: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Send a message to the AI agent and stream the response as Server-Sent Events.
    Also persists the user's message and agent's final message in PostgreSQL.
    """
    org_id = await get_org_id_for_user(user["sub"], pool)

    tenant = None
    async with pool.connection() as conn:
        result = await conn.execute("SELECT * FROM tenants WHERE org_id = %s", (org_id,))
        tenant = await result.fetchone()

    # Determine a valid UUID for the session
    real_session_id = req.session_id
    try:
        uuid.UUID(real_session_id)
    except ValueError:
        # Fallback to namespace UUID if not a valid UUID string
        real_session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{org_id}:{req.session_id}"))

    # Ensure the chat session exists in the DB
    async with pool.connection() as conn:
        s_res = await conn.execute(
            "SELECT session_id FROM public.chat_sessions WHERE session_id = %s AND org_id = %s",
            (real_session_id, org_id)
        )
        s_row = await s_res.fetchone()
        if not s_row:
            await conn.execute(
                """
                INSERT INTO public.chat_sessions (session_id, org_id, user_auth_uid, title)
                VALUES (%s, %s, %s, %s)
                """,
                (real_session_id, org_id, user["sub"], req.message[:50])
            )
        else:
            # Update title if it's the default "New Chat" and this is the first real message
            if s_row.get("title") == "New Chat":
                await conn.execute(
                    "UPDATE public.chat_sessions SET title = %s WHERE session_id = %s",
                    (req.message[:50], real_session_id)
                )

        # Save user's message
        await conn.execute(
            """
            INSERT INTO public.chat_messages (session_id, org_id, role, content)
            VALUES (%s, %s, 'user', %s)
            """,
            (real_session_id, org_id, req.message)
        )
        # Update updated_at of session
        await conn.execute(
            "UPDATE public.chat_sessions SET updated_at = now() WHERE session_id = %s",
            (real_session_id,)
        )

    session = await _get_or_create_session(org_id, real_session_id, tenant)

    async def event_stream():
        try:
            graph = session["graph"]
            config = session["config"]

            if session.get("graph_type") == "analytics":
                graph_input = {
                    "messages": [HumanMessage(content=req.message)],
                    "schema_metadata": session.get("schema_metadata") or {},
                    "tenant_context": session.get("tenant_context") or {},
                }
            else:
                graph_input = {
                    "messages": [HumanMessage(content=req.message)],
                    "yolo_mode": session["yolo_mode"],
                }

            yield f"data: {json.dumps({'type': 'typing', 'status': True})}\n\n"

            message_buffer = ""
            seen_tool_call_ids = set()

            async for message_chunk, metadata in graph.astream(
                input=graph_input,
                stream_mode="messages",
                config=config,
            ):
                if isinstance(message_chunk, AIMessageChunk):
                    # Tool call finish
                    if message_chunk.response_metadata:
                        finish_reason = message_chunk.response_metadata.get("finish_reason", "")
                        if finish_reason == "tool_calls" and message_buffer.strip():
                            yield f"data: {json.dumps({'type': 'message_chunk', 'content': message_buffer})}\n\n"
                            message_buffer = ""

                    # Deduplicate tool calls so only 1 event is emitted per tool call ID
                    if message_chunk.tool_calls:
                        for tc in message_chunk.tool_calls:
                            call_id = tc.get("id") or tc.get("name")
                            if call_id and call_id not in seen_tool_call_ids:
                                seen_tool_call_ids.add(call_id)
                                tool_name = tc.get("name", "")
                                args = tc.get("args", {})
                                yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'args': args})}\n\n"
                    elif message_chunk.tool_call_chunks:
                        tc = message_chunk.tool_call_chunks[0]
                        tool_name = tc.get("name", "")
                        call_id = tc.get("id") or (tool_name if tool_name else None)
                        if tool_name and call_id and call_id not in seen_tool_call_ids:
                            seen_tool_call_ids.add(call_id)
                            args = tc.get("args", "")
                            yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'args': args})}\n\n"
                    elif message_chunk.content:
                        message_buffer += message_chunk.content
                        yield f"data: {json.dumps({'type': 'message_chunk', 'content': message_chunk.content})}\n\n"

            # Final message
            if message_buffer.strip():
                yield f"data: {json.dumps({'type': 'message', 'content': message_buffer, 'is_complete': True})}\n\n"
                
                # Save assistant's response to db
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        INSERT INTO public.chat_messages (session_id, org_id, role, content)
                        VALUES (%s, %s, 'assistant', %s)
                        """,
                        (real_session_id, org_id, message_buffer)
                    )

            # Stop typing
            yield f"data: {json.dumps({'type': 'typing', 'status': False})}\n\n"

            # Check for interrupts (approval requests)
            thread_state = await graph.aget_state(config=config)
            if thread_state.interrupts:
                for interrupt in thread_state.interrupts:
                    yield f"data: {json.dumps({'type': 'approval_request', 'data': interrupt.value, 'interrupt_id': str(uuid.uuid4())})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class ApprovalRequest(BaseModel):
    session_id: str = "default"
    action: str  # "continue", "update", "feedback"
    data: Optional[str] = None

@app.post("/api/chat/approve")
async def chat_approve_endpoint(
    req: ApprovalRequest,
    user: dict = Depends(get_current_user),
):
    """Handle approval response for agent interrupts and persist assistant's subsequent messages."""
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    real_session_id = req.session_id
    try:
        uuid.UUID(real_session_id)
    except ValueError:
        real_session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{org_id}:{req.session_id}"))

    key = f"{org_id}:{real_session_id}"

    if key not in _chat_sessions:
        raise HTTPException(status_code=404, detail="Chat session not found")

    session = _chat_sessions[key]

    async def event_stream():
        try:
            graph = session["graph"]
            config = session["config"]
            resume_input = Command(resume={"action": req.action, "data": req.data})

            yield f"data: {json.dumps({'type': 'typing', 'status': True})}\n\n"

            message_buffer = ""
            async for message_chunk, metadata in graph.astream(
                input=resume_input,
                stream_mode="messages",
                config=config,
            ):
                if isinstance(message_chunk, AIMessageChunk):
                    if message_chunk.tool_call_chunks:
                        tc = message_chunk.tool_call_chunks[0]
                        tool_name = tc.get("name", "")
                        if tool_name:
                            yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'args': tc.get('args', '')})}\n\n"
                    elif message_chunk.content:
                        message_buffer += message_chunk.content
                        yield f"data: {json.dumps({'type': 'message_chunk', 'content': message_chunk.content})}\n\n"

            if message_buffer.strip():
                yield f"data: {json.dumps({'type': 'message', 'content': message_buffer, 'is_complete': True})}\n\n"
                
                # Save assistant's resumed response
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        INSERT INTO public.chat_messages (session_id, org_id, role, content)
                        VALUES (%s, %s, 'assistant', %s)
                        """,
                        (real_session_id, org_id, message_buffer)
                    )

            yield f"data: {json.dumps({'type': 'typing', 'status': False})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Approval stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# REST API Endpoints for Tenancy & Onboarding (Phase 2 & 6)
# ---------------------------------------------------------------------------

class RegisterTenantRequest(BaseModel):
    org_name: str
    agent_name: str = "Ralph"
    backstory: Optional[str] = None
    tone_instructions: Optional[str] = None

@app.post("/auth/register-tenant")
async def register_tenant(
    req: RegisterTenantRequest,
    user: dict = Depends(get_current_user)
):
    """
    Onboarding: Create a new tenant record and link to their Supabase auth account.
    Also creates a corresponding integrations row automatically.
    """
    auth_uid = user["sub"]
    email = user.get("email", "")
    
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")

    try:
        async with pool.connection() as conn:
            # Check if tenant already exists
            result = await conn.execute(
                "SELECT org_id FROM tenants WHERE owner_auth_uid = %s",
                (auth_uid,)
            )
            row = await result.fetchone()
            if row:
                await conn.execute(
                    """
                    UPDATE tenants
                    SET org_name = %s,
                        agent_name = %s,
                        backstory = %s,
                        tone_instructions = %s
                    WHERE org_id = %s
                    """,
                    (
                        req.org_name,
                        req.agent_name,
                        req.backstory,
                        req.tone_instructions,
                        row["org_id"],
                    )
                )
                return {"org_id": str(row["org_id"]), "status": "updated"}
            
            # Create the tenant row
            result = await conn.execute(
                """
                INSERT INTO tenants (owner_email, owner_auth_uid, org_name, agent_name, backstory, tone_instructions)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING org_id
                """,
                (email, auth_uid, req.org_name, req.agent_name, req.backstory, req.tone_instructions)
            )
            row = await result.fetchone()
            org_id = row["org_id"]
            
            # Create placeholder integrations record
            await conn.execute(
                "INSERT INTO integrations (org_id) VALUES (%s)",
                (org_id,)
            )
            
        logger.info(f"Successfully registered tenant {req.org_name} (org_id: {org_id})")
        return {"org_id": str(org_id), "status": "created"}
    except Exception as e:
        logger.error(f"Onboarding registration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Onboarding failed: {str(e)}")

@app.get("/campaigns")
async def get_campaigns(user: dict = Depends(get_current_user)):
    """Fetch all campaigns for the current authenticated tenant (Phase 6)."""
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")

    org_id = await get_org_id_for_user(user["sub"], pool)
    
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                "SELECT * FROM public.marketing_campaigns WHERE org_id = %s ORDER BY created_at DESC",
                (org_id,)
            )
            rows = await result.fetchall()
            return {"campaigns": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"Failed to fetch campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/settings/integrations")
async def get_integrations(user: dict = Depends(get_current_user)):
    """Fetch active integration states and agent details for settings view (Phase 6)."""
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")

    org_id = await get_org_id_for_user(user["sub"], pool)
    
    try:
        async with pool.connection() as conn:
            t_res = await conn.execute(
                "SELECT org_name, agent_name, backstory, tone_instructions, schema_def FROM tenants WHERE org_id = %s",
                (org_id,)
            )
            tenant = await t_res.fetchone()
            
            i_res = await conn.execute(
                "SELECT gmail_access_token, slack_bot_token FROM integrations WHERE org_id = %s",
                (org_id,)
            )
            integration = await i_res.fetchone()
            
        return {
            "agent_name": tenant["agent_name"] if tenant else "Ralph",
            "org_name": tenant["org_name"] if tenant else "BandhanAI",
            "backstory": tenant["backstory"] if tenant else "",
            "tone_instructions": tenant["tone_instructions"] if tenant else "",
            "schema_def": tenant["schema_def"] if tenant else None,
            "integrations": {
                "gmail": bool(integration and integration.get("gmail_access_token")),
                "slack": bool(integration and integration.get("slack_bot_token"))
            }
        }
    except Exception as e:
        logger.error(f"Failed to fetch integration settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def get_root():
    return {"message": "Bandhan AI WebSocket & REST Server", "websocket_url": "/ws/{session_id}"}

@app.get("/health")
async def health_check():
    checkpointer_type = checkpointer.__class__.__name__ if checkpointer else None
    pool_closed = getattr(pool, "closed", None) if pool else None
    return {
        "status": "healthy",
        "database": {
            "configured": bool(SUPABASE_URI),
            "pool_initialized": pool is not None,
            "pool_closed": pool_closed,
        },
        "checkpointer": {
            "initialized": checkpointer is not None,
            "type": checkpointer_type,
            "durable": checkpointer_type not in {None, "MemorySaver"},
        },
        "agent": {
            "yolo_mode_default": YOLO_MODE_DEFAULT,
        },
        "cors": {
            "allowed_origins": BACKEND_CORS_ORIGINS,
        },
        "active_rest_chat_sessions": len(_chat_sessions),
        "timestamp": datetime.now().isoformat()
    }

# Mount static files safely at the very end
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Ensure backend package is in python path
    sys.path.append(str(Path(__file__).parent.parent))
    sys.path.append(str(Path(__file__).parent))
    
    import uvicorn
    # Determine the correct import string based on current path / execution environment
    try:
        import backend.frontend
        app_import = "backend.frontend:app"
    except ImportError:
        app_import = "frontend:app"

    uvicorn.run(
        app_import,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
