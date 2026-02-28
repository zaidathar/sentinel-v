"""Upload endpoints for S3 presigned URL operations.

All endpoints are protected by JWT authentication.
User isolation is enforced: user_sub is always extracted from the JWT,
never from request parameters.
"""

from fastapi import APIRouter, Depends, HTTPException, status
import structlog

from app.core.security import get_current_user, CognitoUser
from app.core.exceptions import (
    FileAccessDeniedError,
    FileValidationError,
    S3Error,
)
from app.models.s3 import (
    UploadRequest,
    PresignedUploadResponse,
    FileMetadata,
    FileListResponse,
)
from app.services.s3 import S3Service, get_s3_service

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/presign",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate presigned upload URL",
    description="Generate a presigned POST URL for direct S3 upload. "
    "The client uploads the file directly to S3 using the returned URL and fields.",
)
async def presign_upload(
    request: UploadRequest,
    current_user: CognitoUser = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service),
):
    """Generate a presigned upload URL for the authenticated user."""
    logger.info(
        "presign_upload_request",
        username=current_user.username,
        filename=request.filename,
        content_type=request.content_type,
        file_size=request.file_size,
    )

    try:
        result = s3_service.generate_upload_url(
            user_sub=current_user.sub,
            filename=request.filename,
            content_type=request.content_type,
            file_size=request.file_size,
        )
        return PresignedUploadResponse(**result)

    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except S3Error as e:
        logger.error("presign_upload_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate upload URL",
        )


@router.get(
    "/files",
    response_model=FileListResponse,
    summary="List uploaded files",
    description="List all files uploaded by the authenticated user.",
)
async def list_files(
    current_user: CognitoUser = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service),
):
    """List all files belonging to the authenticated user."""
    logger.info(
        "list_files_request",
        username=current_user.username,
    )

    try:
        files = s3_service.list_user_files(user_sub=current_user.sub)

        file_metadata_list = [
            FileMetadata(
                object_key=f["object_key"],
                filename=f["filename"],
                size=f["size"],
                uploaded_at=f["uploaded_at"],
            )
            for f in files
        ]

        return FileListResponse(
            files=file_metadata_list,
            count=len(file_metadata_list),
        )

    except S3Error as e:
        logger.error("list_files_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to list files",
        )


@router.get(
    "/files/{object_key:path}",
    response_model=FileMetadata,
    summary="Get file metadata",
    description="Get metadata and a presigned download URL for a specific file.",
)
async def get_file(
    object_key: str,
    current_user: CognitoUser = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service),
):
    """Get file metadata and download URL for the authenticated user."""
    logger.info(
        "get_file_request",
        username=current_user.username,
        object_key=object_key,
    )

    try:
        metadata = s3_service.get_file_metadata(
            user_sub=current_user.sub,
            object_key=object_key,
        )

        download_url = s3_service.generate_download_url(
            user_sub=current_user.sub,
            object_key=object_key,
        )

        return FileMetadata(
            object_key=metadata["object_key"],
            filename=metadata["filename"],
            content_type=metadata["content_type"],
            size=metadata["size"],
            uploaded_at=metadata["uploaded_at"],
            download_url=download_url,
        )

    except FileAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except S3Error as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        logger.error("get_file_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to get file metadata",
        )


@router.delete(
    "/files/{object_key:path}",
    status_code=status.HTTP_200_OK,
    summary="Delete a file",
    description="Delete a file uploaded by the authenticated user.",
)
async def delete_file(
    object_key: str,
    current_user: CognitoUser = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service),
):
    """Delete a file belonging to the authenticated user."""
    logger.info(
        "delete_file_request",
        username=current_user.username,
        object_key=object_key,
    )

    try:
        s3_service.delete_file(
            user_sub=current_user.sub,
            object_key=object_key,
        )

        return {"detail": "File deleted successfully", "object_key": object_key}

    except FileAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except S3Error as e:
        logger.error("delete_file_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to delete file",
        )
