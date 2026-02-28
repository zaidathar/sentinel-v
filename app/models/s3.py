"""Pydantic models for S3 upload operations."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    """Request model for generating a presigned upload URL."""
    
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Original filename (e.g., 'video.mp4')"
    )
    content_type: str = Field(
        ...,
        description="MIME type of the file (e.g., 'video/mp4')"
    )
    file_size: int = Field(
        ...,
        gt=0,
        description="File size in bytes"
    )


class PresignedUploadResponse(BaseModel):
    """Response model containing presigned upload URL and metadata."""
    
    upload_url: str = Field(
        ...,
        description="Presigned POST URL for direct S3 upload"
    )
    fields: dict = Field(
        ...,
        description="Form fields to include in the multipart upload"
    )
    object_key: str = Field(
        ...,
        description="S3 object key for referencing the uploaded file"
    )
    expires_in: int = Field(
        ...,
        description="URL expiration time in seconds"
    )


class FileMetadata(BaseModel):
    """Metadata for an uploaded file."""
    
    object_key: str = Field(
        ...,
        description="S3 object key"
    )
    filename: str = Field(
        ...,
        description="Original filename"
    )
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type of the file"
    )
    size: int = Field(
        ...,
        description="File size in bytes"
    )
    uploaded_at: datetime = Field(
        ...,
        description="Upload timestamp"
    )
    download_url: Optional[str] = Field(
        default=None,
        description="Presigned download URL (if requested)"
    )


class FileListResponse(BaseModel):
    """Response model for listing user's files."""
    
    files: list[FileMetadata] = Field(
        default_factory=list,
        description="List of file metadata objects"
    )
    count: int = Field(
        ...,
        description="Total number of files"
    )
