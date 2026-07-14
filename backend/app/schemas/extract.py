from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.job import JobStatus


class IngestRequest(BaseModel):
    url: HttpUrl
    chunk_size: Annotated[int, Field(ge=200, le=1200)] = 500
    chunk_overlap: Annotated[int, Field(ge=0, le=200)] = 50

    @model_validator(mode="after")
    def overlap_must_be_smaller_than_chunk(self) -> "IngestRequest":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str = Field(validation_alias="id")
    url: str
    status: JobStatus
    title: str | None
    word_count: int | None
    chunk_count: int
    created_at: datetime


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: str
    progress: int
    error: dict[str, str] | None = None


class DocumentMetadata(BaseModel):
    title: str | None
    description: str | None
    site_name: str | None
    author: str | None
    published_at: str | None
    language: str | None
    canonical_url: str
    content_hash: str
    word_count: int


class DocumentChunk(BaseModel):
    index: int
    text: str
    word_count: int


class IngestionResult(BaseModel):
    job_id: str
    status: JobStatus
    metadata: DocumentMetadata
    content: str
    chunks: list[DocumentChunk]
