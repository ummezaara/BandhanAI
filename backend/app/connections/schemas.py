"""Pydantic models for tenant-owned data connection APIs."""

from typing import Any, Literal

from pydantic import BaseModel, Field


ConnectionStatus = Literal["pending", "connected", "failed", "disabled"]


class SupabaseConnectionTestRequest(BaseModel):
    readonly_uri: str = Field(..., min_length=12)
    default_schema: str = "public"


class SupabaseConnectionSaveRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    readonly_uri: str = Field(..., min_length=12)
    project_url: str | None = None
    default_schema: str = "public"
    allowed_schemas: list[str] = Field(default_factory=lambda: ["public"])
    allowed_tables: list[str] = Field(default_factory=list)


class ConnectionHealth(BaseModel):
    ok: bool
    status: ConnectionStatus
    message: str
    database: str | None = None
    current_user: str | None = None
    default_schema: str = "public"
    table_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class TenantDataConnection(BaseModel):
    connection_id: str
    org_id: str
    provider: str
    display_name: str
    project_url: str | None
    default_schema: str
    allowed_schemas: list[str]
    allowed_tables: list[str]
    status: ConnectionStatus
    last_health_check_at: str | None
    last_error: str | None
    created_at: str | None
    updated_at: str | None


class ConnectionsListResponse(BaseModel):
    connections: list[TenantDataConnection]


class SaveConnectionResponse(BaseModel):
    connection: TenantDataConnection
    health: ConnectionHealth


class DeleteConnectionResponse(BaseModel):
    deleted: bool
    connection_id: str


MappingStatus = Literal["draft", "approved", "rejected", "superseded"]


class CustomerFieldCandidate(BaseModel):
    source_column: str
    canonical_field: str
    confidence: float
    reason: str


class CustomerMapping(BaseModel):
    mapping_id: str
    org_id: str
    connection_id: str
    schema_name: str
    table_name: str
    status: MappingStatus
    field_map: dict[str, CustomerFieldCandidate]
    confidence: float
    reasoning: str
    safe_preview: list[dict[str, Any]]
    missing_fields: list[str]
    approved_by: str | None
    approved_at: str | None
    created_at: str | None
    updated_at: str | None


class CustomerDiscoveryResponse(BaseModel):
    mapping: CustomerMapping | None
    candidates: list[CustomerMapping]


class CustomerMappingResponse(BaseModel):
    mapping: CustomerMapping | None


class CustomerMappingFieldUpdateRequest(BaseModel):
    field_assignments: dict[str, str | None]


class SchemaMetadata(BaseModel):
    metadata_id: str
    org_id: str
    connection_id: str
    entity_map: dict[str, str]
    column_catalog: list[dict[str, Any]]
    join_paths: list[dict[str, Any]]
    table_catalog: list[dict[str, Any]]
    confidence: float | None = None
    errors: list[str] = Field(default_factory=list)
    discovered_at: str | None = None


class SchemaMetadataResponse(BaseModel):
    metadata: SchemaMetadata | None


JsonDict = dict[str, Any]
