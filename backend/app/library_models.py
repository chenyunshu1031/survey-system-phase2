"""Inputs for personal question banks and immutable question versions."""

from pydantic import Field, field_validator, model_validator

from app.models import ApiModel, QuestionEditInput


class QuestionBankInput(ApiModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def tidy_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("题库名称不能为空")
        return value


class LibraryVersionInput(QuestionEditInput):
    parent_version_id: str


class BankItemInput(ApiModel):
    library_question_id: str
    selected_version_id: str


class BankItemVersionInput(ApiModel):
    expected_version_id: str
    selected_version_id: str


class ShareInput(ApiModel):
    recipient_user_id: str | None = None
    recipient_username: str | None = Field(default=None, min_length=3, max_length=40)

    @model_validator(mode="after")
    def one_recipient(self) -> "ShareInput":
        if (self.recipient_user_id is None) == (self.recipient_username is None):
            raise ValueError("只能指定接收者用户 ID 或用户名其中之一")
        if self.recipient_username is not None:
            self.recipient_username = self.recipient_username.strip()
            if len(self.recipient_username) < 3 or any(char.isspace() for char in self.recipient_username):
                raise ValueError("接收者用户名格式无效")
        return self


class SurveyLibraryQuestionInput(ApiModel):
    library_question_id: str
    version_id: str
