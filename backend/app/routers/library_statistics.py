"""Automatic aggregate statistics with legacy consent routes."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.db import get_db
from app.security import current_user
from app.services.library_statistics import (
    all_version_statistics, get_consent, question_overview_statistics,
    set_consent, version_statistics,
)


survey_router = APIRouter(prefix="/api/v1/surveys", tags=["cross survey statistics"])
library_router = APIRouter(prefix="/api/v1/library/questions", tags=["cross survey statistics"])


@survey_router.get("/{survey_id}/cross-survey-statistics/{question_id}/consent")
def read_consent(
    survey_id: str, question_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return get_consent(db, survey_id, question_id, user["_id"])


@survey_router.put("/{survey_id}/cross-survey-statistics/{question_id}/consent")
def grant_consent(
    survey_id: str, question_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return set_consent(db, survey_id, question_id, user["_id"], grant=True)


@survey_router.delete("/{survey_id}/cross-survey-statistics/{question_id}/consent")
def revoke_consent(
    survey_id: str, question_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return set_consent(db, survey_id, question_id, user["_id"], grant=False)


@library_router.get("/{question_id}/versions/{version_id}/cross-survey-statistics")
def get_version_statistics(
    question_id: str, version_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return version_statistics(db, question_id, version_id, user["_id"])


@library_router.get("/{question_id}/versions/{version_id}/all-survey-statistics")
def get_all_version_statistics(
    question_id: str, version_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return all_version_statistics(db, question_id, version_id, user["_id"])


@library_router.get("/{question_id}/all-survey-statistics")
def get_question_overview_statistics(
    question_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return question_overview_statistics(db, question_id, user["_id"])
