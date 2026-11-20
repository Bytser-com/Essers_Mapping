"""Data models for the Mapping Converter: the JSON mapping package and API responses."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MappingEntry(BaseModel):
    """Single mapping rule between a source path and a target path."""

    source_path: str | None = Field(
        default=None,
        description='XPath-like path in the source XML document',
    )
    target_path: str = Field(
        ...,
        description='Full target path in the H.Essers standardized schema',
    )


class PackageMeta(BaseModel):
    """Metadata header for the mapping package."""

    client_name: str = Field(..., description='Customer / client name')
    package_version: str = Field(..., description='Package version, e.g. 1.0.0')
    package_type: str = Field(..., description='Proposal / package type, e.g. inbound or outbound')
    date_created: str = Field(..., description='ISO 8601 creation timestamp')
    user_created: str = Field(default='analist_a', description='Author or analyst identifier')
    description: str | None = Field(default=None, description='What changed in this version (from the approval)')
    approved_at: str | None = Field(default=None, description='ISO 8601 time the analyst approved the proposal')


class MappingPackage(BaseModel):
    """Collection of mapping rules constituting a JSON mapping package."""

    schema_version: str = Field(default='1.0', description='Schema version of the package')
    meta: PackageMeta | None = Field(default=None, description='Package metadata header')
    mappings: list[MappingEntry] = Field(
        default_factory=list,
        description='List of mapped source and target field pairs',
    )


class SavePackageResponse(BaseModel):
    """Response returned when an Excel proposal is converted and stored as a mapping package."""

    status: str = Field(default='success', description='Status of the operation')
    sftp_path: str = Field(..., description='Full path on the SFTP server where MPackage.json is stored')
    sftp_server: str = Field(..., description='The SFTP server where the file was stored, or local-filesystem')
    company: str = Field(..., description='Normalized company name')
    version: str = Field(..., description='Version tag, e.g. v3 or v4')
    proposal_type: str = Field(..., description='Proposal type, e.g. inbound or outbound')
    filename: str = Field(default='MPackage.json', description='Filename on the SFTP server')
    mapping_count: int = Field(..., description='Total count of mapped fields')
    package: MappingPackage = Field(..., description='The parsed JSON mapping package with metadata')
