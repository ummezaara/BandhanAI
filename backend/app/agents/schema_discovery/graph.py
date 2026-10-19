"""Entry point for the schema discovery workflow."""

from __future__ import annotations

from typing import TypedDict

from backend.app.agents.schema_discovery.service import run_schema_discovery


class SchemaDiscoveryState(TypedDict, total=False):
    connection_id: str
    org_id: str
    metadata: dict
    errors: list[str]


async def run_graph(pg_pool, state: SchemaDiscoveryState) -> SchemaDiscoveryState:
    """Run discovery as a compact workflow entry point."""
    metadata = await run_schema_discovery(
        pg_pool=pg_pool,
        org_id=state["org_id"],
        connection_id=state["connection_id"],
    )
    return {**state, "metadata": metadata, "errors": metadata.get("errors", [])}
