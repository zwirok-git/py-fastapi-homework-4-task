from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.dependencies import get_jwt_auth_manager, get_s3_storage_client
from database import get_db, UserModel, UserProfileModel
from exceptions import S3FileUploadError
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from security.interfaces import JWTAuthManagerInterface
from storages import S3StorageInterface

router = APIRouter()
ADMIN_GROUP_ID = 3

DBSession = Annotated[AsyncSession, Depends(get_db)]
JWTManager = Annotated[JWTAuthManagerInterface, Depends(get_jwt_auth_manager)]
S3Client = Annotated[S3StorageInterface, Depends(get_s3_storage_client)]


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid "
                   "Authorization header format. Expected 'Bearer <token>'",
        )
    return token


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_profile(
    user_id: int,
    request: Request,
    db: DBSession,
    jwt_manager: JWTManager,
    s3_client: S3Client,
) -> ProfileResponseSchema:
    token = _extract_bearer_token(request)

    try:
        token_data = jwt_manager.decode_access_token(token)
    except Exception as exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exception)
        )
    token_user_id = token_data.get("user_id")

    if token_user_id != user_id:
        stmt = select(UserModel).where(UserModel.id == token_user_id)
        result = await db.execute(stmt)
        requesting_user = result.scalars().first()

        if not requesting_user or requesting_user.group_id != ADMIN_GROUP_ID:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this profile.",
            )

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    target_user = result.scalars().first()

    if not target_user or not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    form = await request.form()

    try:
        profile_data = ProfileCreateSchema(
            first_name=form.get("first_name"),
            last_name=form.get("last_name"),
            gender=form.get("gender"),
            date_of_birth=form.get("date_of_birth"),
            info=form.get("info"),
            avatar=form.get("avatar"),
        )
    except ValidationError as exception:
        raise RequestValidationError(errors=exception.errors())

    avatar_name = f"avatars/{user_id}_avatar.jpg"

    await profile_data.avatar.seek(0)
    avatar_content = await profile_data.avatar.read()

    try:
        await s3_client.upload_file(
            file_data=avatar_content, file_name=avatar_name
        )
    except S3FileUploadError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later.",
        )

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name.lower(),
        last_name=profile_data.last_name.lower(),
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_name,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    avatar_url = await s3_client.get_file_url(avatar_name)

    return ProfileResponseSchema(
        id=new_profile.id,
        user_id=new_profile.user_id,
        first_name=new_profile.first_name,
        last_name=new_profile.last_name,
        gender=new_profile.gender,
        date_of_birth=new_profile.date_of_birth,
        info=new_profile.info,
        avatar=avatar_url,
    )