"""HTTP routes for tenant-owned Supabase connections."""

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.connections.schemas import (
    ConnectionHealth,
    ConnectionsListResponse,
    CustomerMappingFieldUpdateRequest,
    CustomerDiscoveryResponse,
    CustomerMappingResponse,
    DeleteConnectionResponse,
    SaveConnectionResponse,
    SchemaMetadataResponse,
    SupabaseConnectionSaveRequest,
    SupabaseConnectionTestRequest,
)
from backend.app.connections import service
from backend.app.connections import discovery
from backend.app.connections import metadata
from backend.app.agents.schema_discovery.service import run_schema_discovery
from backend.auth import get_current_user, get_org_id_for_user
from backend.app.audit.service import log_audit_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connections", tags=["connections"])

_pg_pool = None


def set_pg_pool(pool):
    """Called by frontend.py at startup to inject the shared connection pool."""
    global _pg_pool
    _pg_pool = pool


def _get_pool():
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized.")
    return _pg_pool


@router.post("/supabase/test", response_model=ConnectionHealth)
async def test_supabase_connection(
    req: SupabaseConnectionTestRequest,
    user: dict = Depends(get_current_user),
):
    """Test a read-only Supabase/Postgres connection string without saving it."""
    pool = _get_pool()
    await get_org_id_for_user(user["sub"], pool)

    try:
        return await service.test_supabase_connection(
            req.readonly_uri,
            req.default_schema,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/supabase", response_model=SaveConnectionResponse)
async def save_supabase_connection(
    req: SupabaseConnectionSaveRequest,
    user: dict = Depends(get_current_user),
):
    """Save an encrypted tenant-owned Supabase read-only connection."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        connection, health = await service.save_connection(
            pg_pool=pool,
            org_id=org_id,
            display_name=req.display_name.strip(),
            readonly_uri=req.readonly_uri,
            project_url=req.project_url,
            default_schema=req.default_schema.strip() or "public",
            allowed_schemas=req.allowed_schemas or ["public"],
            allowed_tables=req.allowed_tables or [],
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="supabase_connect",
            details={
                "display_name": req.display_name.strip(),
                "default_schema": req.default_schema.strip() or "public",
                "status": connection.get("status")
            }
        )
        return {"connection": connection, "health": health}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        frames = "".join(traceback.format_list(traceback.extract_tb(exc.__traceback__)))
        logger.error(
            "Failed to save Supabase connection; exception_type=%s\n%s",
            type(exc).__name__,
            frames,
        )
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        frames = "".join(traceback.format_list(traceback.extract_tb(exc.__traceback__)))
        logger.error(
            "Unhandled failure saving Supabase connection; exception_type=%s\n%s",
            type(exc).__name__,
            frames,
        )
        raise


@router.get("", response_model=ConnectionsListResponse)
async def list_tenant_connections(user: dict = Depends(get_current_user)):
    """List safe connection metadata for the authenticated tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    connections = await service.list_connections(pool, org_id)
    return {"connections": connections}


@router.delete("/{connection_id}", response_model=DeleteConnectionResponse)
async def delete_tenant_connection(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a tenant connection and its encrypted credential."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    deleted = await service.delete_connection(pool, org_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return {"deleted": True, "connection_id": connection_id}


@router.post("/{connection_id}/health-check", response_model=ConnectionHealth)
async def health_check_tenant_connection(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    """Re-test a saved tenant Supabase connection."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        return await service.health_check_connection(pool, org_id, connection_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    except RuntimeError as exc:
        logger.error("Connection health check failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{connection_id}/discover/customers", response_model=CustomerDiscoveryResponse)
async def discover_customer_mapping(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    """Discover likely customer tables for a saved tenant Supabase connection."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        return await discovery.discover_customer_tables(pool, org_id, connection_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    except RuntimeError as exc:
        logger.error("Customer discovery failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Customer discovery failed")
        raise HTTPException(status_code=500, detail=f"Customer discovery failed: {exc}")


@router.post("/{connection_id}/discover/schema", response_model=SchemaMetadataResponse)
async def discover_schema_metadata(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    """Discover and cache a full multi-table schema map for a tenant connection."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        result = await run_schema_discovery(pool, org_id, connection_id)
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="schema_discovery_run",
            details={
                "connection_id": connection_id,
                "entity_map": result.get("entity_map", {}),
                "confidence": result.get("confidence"),
                "errors": result.get("errors", []),
            },
        )
        return {"metadata": result}
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    except Exception as exc:
        logger.exception("Schema discovery failed")
        raise HTTPException(status_code=500, detail=f"Schema discovery failed: {exc}")


@router.get("/{connection_id}/schema-metadata", response_model=SchemaMetadataResponse)
async def get_connection_schema_metadata(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    """Return cached multi-table schema metadata for a tenant connection."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    result = await metadata.get_schema_metadata(pool, org_id, connection_id)
    return {"metadata": result}


@router.get("/{connection_id}/customer-mapping", response_model=CustomerMappingResponse)
async def get_customer_mapping(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the latest approved or draft customer mapping for a connection."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    mapping = await discovery.get_latest_customer_mapping(pool, org_id, connection_id)
    return {"mapping": mapping}


@router.post("/customer-mappings/{mapping_id}/approve", response_model=CustomerMappingResponse)
async def approve_customer_mapping(
    mapping_id: str,
    user: dict = Depends(get_current_user),
):
    """Approve a draft customer mapping for agent use."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        mapping = await discovery.set_mapping_status(
            pool,
            org_id,
            mapping_id,
            "approved",
            approved_by=user["sub"],
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="schema_map_approve",
            details={
                "mapping_id": mapping_id,
                "table_name": mapping.get("table_name"),
                "status": mapping.get("status")
            }
        )
        return {"mapping": mapping}
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")


@router.put("/customer-mappings/{mapping_id}/fields", response_model=CustomerMappingResponse)
async def update_customer_mapping_fields(
    mapping_id: str,
    request: CustomerMappingFieldUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Update explicitly assigned risk fields on a tenant-owned customer mapping."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        mapping = await discovery.update_customer_mapping_fields(
            pool,
            org_id,
            mapping_id,
            request.field_assignments,
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="schema_map_fields_update",
            details={"mapping_id": mapping_id, "field_assignments": request.field_assignments},
        )
        return {"mapping": mapping}
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/customer-mappings/{mapping_id}/reject", response_model=CustomerMappingResponse)
async def reject_customer_mapping(
    mapping_id: str,
    user: dict = Depends(get_current_user),
):
    """Reject a draft customer mapping."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        mapping = await discovery.set_mapping_status(
            pool,
            org_id,
            mapping_id,
            "rejected",
        )
        return {"mapping": mapping}
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
