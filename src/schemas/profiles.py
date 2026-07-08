from datetime import date

from fastapi import UploadFile
from pydantic import BaseModel, field_validator, ConfigDict

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)


class ProfileCreateSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile

    @field_validator("first_name", "last_name")
    @classmethod
    def check_name(cls, name: str) -> str:
        validate_name(name)
        return name

    @field_validator("gender")
    @classmethod
    def check_gender(cls, gender: str) -> str:
        validate_gender(gender)
        return gender

    @field_validator("date_of_birth")
    @classmethod
    def check_birth_date(cls, birth_date: date) -> date:
        validate_birth_date(birth_date)
        return birth_date

    @field_validator("info")
    @classmethod
    def check_info(cls, information: str) -> str:
        if not information or not information.strip():
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return information

    @field_validator("avatar")
    @classmethod
    def check_avatar(cls, avatar: UploadFile) -> UploadFile:
        validate_image(avatar)
        return avatar


class ProfileResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str
