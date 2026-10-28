"""Sharing, survey snapshots, and minimal use tracking for library questions."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Iterator

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.services.library import committed_version, owned_library_question
from app.services.surveys import parse_object_id, utc_datetime


CONTENT_FIELDS = ("type", "title", "required", "options", "validation")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def share_view(share: dict, db: Database) -> dict:
    recipient = db.users.find_one({"_id": share["recipientUserId"]}, {"username": 1})
    return {
        "recipientUserId": str(share["recipientUserId"]),
        "recipientUsername": recipient["username"] if recipient else None,
        "createdAt": utc_datetime(share["createdAt"]),
    }


def grant_share(db: Database, question_id: str, owner_id: ObjectId, recipient_id: str) -> tuple[dict, bool]:
    question = owned_library_question(db, question_id, owner_id)
    recipient = parse_object_id(recipient_id)
    if recipient == owner_id:
        raise HTTPException(status_code=422, detail="无需分享给题目所有者")
    if db.users.find_one({"_id": recipient}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="接收用户不存在")
    key = {"libraryQuestionId": question["_id"], "recipientUserId": recipient}
    share = db.questionShares.find_one(key)
    if share is None:
        document = {
            **key, "grantedById": owner_id, "createdAt": _now(),
            "activeSelections": 0, "schemaVersion": 2,
        }
        try:
            document["_id"] = db.questionShares.insert_one(document).inserted_id
            return document, False
        except DuplicateKeyError:
            share = db.questionShares.find_one(key)
    if share is None:
        raise HTTPException(status_code=409, detail="分享授权冲突，请重试")
    if share.get("revokedAt") is None:
        return share, True
    result = db.questionShares.update_one({
        **key, "_id": share["_id"], "revokedAt": share["revokedAt"],
        "activeSelections": {"$in": [0, None]},
    }, {"$set": {"grantedById": owner_id, "createdAt": _now()}, "$unset": {"revokedAt": ""}})
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="分享授权状态已变化，请重试")
    return db.questionShares.find_one({"_id": share["_id"]}), False


def revoke_share(db: Database, question_id: str, owner_id: ObjectId, recipient_id: str) -> None:
    question = owned_library_question(db, question_id, owner_id)
    key = {"libraryQuestionId": question["_id"], "recipientUserId": parse_object_id(recipient_id)}
    share = db.questionShares.find_one(key)
    if share is None:
        raise HTTPException(status_code=404, detail="分享授权不存在")
    if share.get("revokedAt") is not None:
        return
    result = db.questionShares.update_one({
        **key, "_id": share["_id"], "revokedAt": None,
        "activeSelections": {"$in": [0, None]},
    }, {"$set": {"revokedAt": _now()}})
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="授权正在用于选题或状态已变化，请稍后重试")


def accessible_library_question(db: Database, question_id: str, user_id: ObjectId) -> dict:
    question = db.libraryQuestions.find_one({"_id": parse_object_id(question_id)})
    if question is None or not question.get("currentVersionId"):
        raise HTTPException(status_code=404, detail="题库题目不存在")
    if question["ownerId"] != user_id and db.questionShares.find_one({
        "libraryQuestionId": question["_id"], "recipientUserId": user_id, "revokedAt": None,
    }) is None:
        raise HTTPException(status_code=404, detail="题库题目不存在")
    return question


@contextmanager
def reserve_shared_selection(db: Database, question: dict, user_id: ObjectId) -> Iterator[None]:
    if question["ownerId"] == user_id:
        yield
        return
    result = db.questionShares.update_one({
        "libraryQuestionId": question["_id"], "recipientUserId": user_id, "revokedAt": None,
    }, {"$inc": {"activeSelections": 1}})
    if result.matched_count != 1:
        raise HTTPException(status_code=404, detail="题目分享已撤销或不存在")
    try:
        yield
    finally:
        db.questionShares.update_one({
            "libraryQuestionId": question["_id"], "recipientUserId": user_id,
        }, {"$inc": {"activeSelections": -1}})


def validate_source_reference(db: Database, question: dict) -> None:
    """Old questions may have no source; sourced snapshots must match a committed version."""
    has_question = "sourceLibraryQuestionId" in question
    has_version = "sourceVersionId" in question
    if not has_question and not has_version:
        return
    if not (has_question and has_version):
        raise ValueError("来源题目与版本必须成对存在")
    logical_id = question["sourceLibraryQuestionId"]
    version_id = question["sourceVersionId"]
    if not isinstance(logical_id, ObjectId) or not isinstance(version_id, ObjectId):
        raise ValueError("来源标识类型无效")
    logical = db.libraryQuestions.find_one({"_id": logical_id})
    if logical is None:
        raise ValueError("来源题目不存在")
    try:
        version = committed_version(db, logical, version_id)
    except HTTPException as error:
        raise ValueError("来源版本不存在或不属于来源题目") from error
    if any(question.get(name) != version.get(name) for name in CONTENT_FIELDS):
        raise ValueError("问卷题目内容与来源版本不一致")


def version_snapshot(survey_id: ObjectId, order: int, logical: dict, version: dict) -> dict:
    return {
        "surveyId": survey_id,
        "order": order,
        **{name: deepcopy(version[name]) for name in CONTENT_FIELDS},
        "jumpRules": [],
        "sourceLibraryQuestionId": logical["_id"],
        "sourceVersionId": version["_id"],
        "schemaVersion": 1,
    }


def list_usages(db: Database, question_id: str, owner_id: ObjectId) -> list[dict]:
    logical = owned_library_question(db, question_id, owner_id)
    items = []
    for question in db.questions.find({
        "sourceLibraryQuestionId": logical["_id"], "sourceVersionId": {"$exists": True},
    }).sort([("surveyId", 1), ("order", 1)]):
        survey = db.surveys.find_one({"_id": question["surveyId"]}, {"ownerId": 1, "status": 1})
        if survey is None:
            continue
        try:
            validate_source_reference(db, question)
        except ValueError:
            continue
        items.append({
            "surveyId": str(survey["_id"]),
            "questionId": str(question["_id"]),
            "versionId": str(question["sourceVersionId"]),
            "status": survey["status"],
            "isOwnSurvey": survey["ownerId"] == owner_id,
        })
    return items
