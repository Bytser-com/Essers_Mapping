"""Data models for Mapping Converter."""

from pydantic import BaseModel, Field


class MappingEntry(BaseModel):
    """Single mapping rule between a source path and a target path."""

    source_path: str | None = Field(
        default=None,
        description="XPath-like path in the source XML document",
    )
    target_path: str = Field(
        ...,
        description="Full target path in the H.Essers standardized schema",
    )


class MappingPackage(BaseModel):
    """Collection of mapping rules constituting a JSON mapping package."""

    mappings: list[MappingEntry] = Field(
        default_factory=list,
        description="List of mapped source and target field pairs",
    )
