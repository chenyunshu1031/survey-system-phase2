"""Personal question banks and immutable versions on standalone MongoDB."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.library_models import LibraryVersionInput, QuestionBankInput
from app.models import QuestionInput
from app.services.surveys import parse_object_id, utc_datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def owned_library_question(db: Database, question_id: str, owner_id: ObjectId) -> dict:
    question = db.libraryQuestions.find_one({"_id": parse_object_id(question_id), "ownerId": owner_id})
    if question is None:
        raise HTTPException(status_code=404, detail="题库题目不存在")
    return question


def owned_bank(db: Database, bank_id: str, owner_id: ObjectId) -> dict:
    bank = db.questionBanks.find_one({"_id": parse_object_id(bank_id), "ownerId": owner_id, "deletedAt": None})
    if bank is None:
        raise HTTPException(status_code=404, detail="题库不存在")
    return bank


def committed_version(db: Database, question: dict, version_id: str | ObjectId) -> dict:
    identifier = version_id if isinstance(version_id, ObjectId) else parse_object_id(version_id)
    version = db.questionVersions.find_one({"_id": identifier, "libraryQuestionId": question["_id"]})
    if version is None or version["versionNo"] > question.get("versionCounter", 0):
        raise HTTPException(status_code=404, detail="题目版本不存在")
    return version


def version_view(version: dict) -> dict:
    return {
        "id": str(version["_id"]),
        "libraryQuestionId": str(version["libraryQuestionId"]),
        "versionNo": version["versionNo"],
        "parentVersionId": str(version["parentVersionId"]) if version["parentVersionId"] else None,
        "createdById": str(version["createdById"]),
        "type": version["type"],
        "title": version["title"],
        "required": version["required"],
        "options": version["options"],
        "validation": version["validation"],
        "createdAt": utc_datetime(version["createdAt"]),
    }


def library_question_view(db: Database, question: dict) -> dict:
    current_id = question.get("currentVersionId")
    current = db.questionVersions.find_one({"_id": current_id}) if current_id else None
    return {
        "id": str(question["_id"]),
        "ownerId": str(question["ownerId"]),
        "currentVersionId": str(current_id) if current_id else None,
        "currentVersion": version_view(current) if current else None,
        "createdAt": utc_datetime(question["createdAt"]),
        "updatedAt": utc_datetime(question["updatedAt"]),
    }


def bank_view(bank: dict) -> dict:
    return {
        "id": str(bank["_id"]), "name": bank["name"],
        "createdAt": utc_datetime(bank["createdAt"]),
        "updatedAt": utc_datetime(bank["updatedAt"]),
    }


def bank_item_view(db: Database, item: dict) -> dict:
    version = db.questionVersions.find_one({"_id": item["selectedVersionId"]})
    return {
        "id": str(item["_id"]), "bankId": str(item["bankId"]),
        "libraryQuestionId": str(item["libraryQuestionId"]),
        "selectedVersionId": str(item["selectedVersionId"]),
        "selectedVersion": version_view(version) if version else None,
        "createdAt": utc_datetime(item["createdAt"]),
        "updatedAt": utc_datetime(item.get("updatedAt", item["createdAt"])),
    }


def _initial_content(payload: QuestionInput) -> dict:
    return {
        "type": payload.type, "title": payload.title, "required": payload.required,
        "options": [{"id": uuid4().hex, "label": label} for label in payload.options],
        "validation": payload.validation.model_dump(by_alias=True, exclude_none=True),
    }


def _edited_content(payload: LibraryVersionInput, parent: dict) -> dict:
    previous_ids = {option["id"] for option in parent["options"]}
    used_ids: set[str] = set()
    options = []
    for option in payload.options:
        option_id = option.id or uuid4().hex
        if option.id and (option_id not in previous_ids or option_id in used_ids):
            raise HTTPException(status_code=422, detail="选项 ID 不属于来源版本或重复使用")
        used_ids.add(option_id)
        options.append({"id": option_id, "label": option.label})
    return {
        "type": payload.type, "title": payload.title, "required": payload.required,
        "options": options,
        "validation": payload.validation.model_dump(by_alias=True, exclude_none=True),
    }


def _finalize_pending(db: Database, question: dict, version: dict) -> None:
    version_id = question["pendingVersionId"]
    number = question["pendingVersionNo"]
    if (version["_id"] != version_id or version["libraryQuestionId"] != question["_id"]
            or version["versionNo"] != number
            or version["requestFingerprint"] != question["pendingFingerprint"]):
        raise _conflict("待完成版本与题目预占记录不一致")
    result = db.libraryQuestions.update_one({
        "_id": question["_id"], "ownerId": question["ownerId"],
        "pendingVersionId": version_id,
        "currentVersionId": question["pendingExpectedCurrentVersionId"],
        "versionCounter": number - 1,
    }, {
        "$set": {"currentVersionId": version_id, "versionCounter": number, "updatedAt": _now()},
        "$unset": {
            "pendingVersionId": "", "pendingRequestId": "", "pendingFingerprint": "",
            "pendingExpectedCurrentVersionId": "", "pendingVersionNo": "",
        },
    })
    if result.matched_count == 1:
        return
    latest = db.libraryQuestions.find_one({"_id": question["_id"]})
    if latest and latest.get("currentVersionId") == version_id and latest.get("versionCounter") == number:
        return  # Another retry completed the same request.
    raise _conflict("题目当前版本已变化，请重新读取")


def _finish_pending(
    db: Database, question: dict, owner_id: ObjectId, request_id: str,
    fingerprint: str, parent_id: ObjectId | None, content: dict,
) -> dict:
    if (question.get("pendingRequestId") != request_id
            or question.get("pendingFingerprint") != fingerprint):
        raise _conflict("已有另一项版本写入正在进行，请稍后重试")
    version_id = question["pendingVersionId"]
    version = {
        "_id": version_id, "libraryQuestionId": question["_id"],
        "versionNo": question["pendingVersionNo"], "parentVersionId": parent_id,
        "createdById": owner_id, "requestId": request_id,
        "requestFingerprint": fingerprint, **content,
        "createdAt": _now(), "schemaVersion": 2,
    }
    try:
        db.questionVersions.insert_one(version)
    except DuplicateKeyError:
        saved = db.questionVersions.find_one({"_id": version_id})
        if saved is None or saved["requestId"] != request_id or saved["requestFingerprint"] != fingerprint:
            raise _conflict("版本号或重复请求标识冲突") from None
        version = saved
    _finalize_pending(db, question, version)
    return version


def create_library_question(
    db: Database, owner_id: ObjectId, payload: QuestionInput, request_id: str,
    *, source_survey_id: ObjectId | None = None, source_question_id: ObjectId | None = None,
) -> tuple[dict, dict, bool]:
    fingerprint_input = {"operation": "create", "question": payload.model_dump(by_alias=True, exclude_none=True)}
    if source_question_id is not None:
        fingerprint_input = {**fingerprint_input, "operation": "import", "sourceQuestionId": str(source_question_id)}
    fingerprint = _fingerprint(fingerprint_input)
    if source_question_id is not None:
        prior_import = db.libraryQuestions.find_one({
            "ownerId": owner_id, "importedFromQuestionId": source_question_id,
        })
        if prior_import is not None and prior_import["creationRequestId"] != request_id:
            raise _conflict("这道问卷题目已保存为可复用题目")
    existing = db.libraryQuestions.find_one({"ownerId": owner_id, "creationRequestId": request_id})
    if existing is None:
        now = _now()
        existing = {
            "_id": ObjectId(), "ownerId": owner_id,
            "creationRequestId": request_id, "creationFingerprint": fingerprint,
            "currentVersionId": None, "versionCounter": 0,
            "pendingVersionId": ObjectId(), "pendingRequestId": request_id,
            "pendingFingerprint": fingerprint, "pendingExpectedCurrentVersionId": None,
            "pendingVersionNo": 1, "createdAt": now, "updatedAt": now, "schemaVersion": 2,
        }
        if source_question_id is not None and source_survey_id is not None:
            existing["importedFromSurveyId"] = source_survey_id
            existing["importedFromQuestionId"] = source_question_id
        try:
            db.libraryQuestions.insert_one(existing)
        except DuplicateKeyError:
            existing = db.libraryQuestions.find_one({"ownerId": owner_id, "creationRequestId": request_id})
            if existing is None and source_question_id is not None:
                raise _conflict("这道问卷题目已保存为可复用题目") from None
        else:
            version = _finish_pending(db, existing, owner_id, request_id, fingerprint, None, _initial_content(payload))
            return db.libraryQuestions.find_one({"_id": existing["_id"]}), version, False
    if existing is None or existing["creationFingerprint"] != fingerprint:
        raise _conflict("重复请求标识已用于不同题目")
    if existing.get("currentVersionId"):
        version = db.questionVersions.find_one({"_id": existing["currentVersionId"]})
        if version is None:
            raise _conflict("题目当前版本缺失")
        return existing, version, True
    version = _finish_pending(db, existing, owner_id, request_id, fingerprint, None, _initial_content(payload))
    return db.libraryQuestions.find_one({"_id": existing["_id"]}), version, True


def _create_version(
    db: Database, question: dict, owner_id: ObjectId, request_id: str,
    fingerprint: str, parent_id: ObjectId, content: dict,
) -> tuple[dict, bool]:
    previous = db.questionVersions.find_one({"libraryQuestionId": question["_id"], "requestId": request_id})
    if previous:
        if previous["requestFingerprint"] != fingerprint:
            raise _conflict("重复请求标识已用于不同版本内容")
        if question.get("pendingVersionId") == previous["_id"]:
            _finalize_pending(db, question, previous)
        elif previous["versionNo"] > question.get("versionCounter", 0):
            raise _conflict("版本写入尚未完成，请使用原请求标识重试")
        return previous, True
    if question.get("pendingVersionId"):
        if question.get("pendingRequestId") == request_id:
            version = _finish_pending(db, question, owner_id, request_id, fingerprint, parent_id, content)
            return version, True
        pending = db.questionVersions.find_one({"_id": question["pendingVersionId"]})
        if pending is None:
            raise _conflict("另一版本写入尚未完成；请用原请求标识重试")
        _finalize_pending(db, question, pending)
        question = db.libraryQuestions.find_one({"_id": question["_id"]})
    if not question.get("currentVersionId"):
        raise _conflict("题目首版本尚未完成；请用原请求标识重试")
    version_id = ObjectId()
    result = db.libraryQuestions.update_one({
        "_id": question["_id"], "ownerId": owner_id,
        "currentVersionId": question["currentVersionId"],
        "versionCounter": question["versionCounter"], "pendingVersionId": None,
    }, {"$set": {
        "pendingVersionId": version_id, "pendingRequestId": request_id,
        "pendingFingerprint": fingerprint,
        "pendingExpectedCurrentVersionId": question["currentVersionId"],
        "pendingVersionNo": question["versionCounter"] + 1,
    }})
    if result.matched_count != 1:
        # A simultaneous request with the same key may have reserved or completed.
        current = db.libraryQuestions.find_one({"_id": question["_id"], "ownerId": owner_id})
        if current and current.get("pendingRequestId") == request_id:
            version = _finish_pending(db, current, owner_id, request_id, fingerprint, parent_id, content)
            return version, True
        latest = db.questionVersions.find_one({"libraryQuestionId": question["_id"], "requestId": request_id})
        if latest and latest["requestFingerprint"] == fingerprint:
            current = db.libraryQuestions.find_one({"_id": question["_id"]})
            if current and latest["versionNo"] <= current.get("versionCounter", 0):
                return latest, True
        raise _conflict("题目版本正在变化，请重新读取后重试")
    reserved = db.libraryQuestions.find_one({"_id": question["_id"]})
    version = _finish_pending(db, reserved, owner_id, request_id, fingerprint, parent_id, content)
    return version, False


def create_version(
    db: Database, question: dict, owner_id: ObjectId,
    payload: LibraryVersionInput, request_id: str,
) -> tuple[dict, bool]:
    parent = committed_version(db, question, payload.parent_version_id)
    fingerprint = _fingerprint({"operation": "edit", "parentVersionId": str(parent["_id"]),
                                "content": payload.model_dump(by_alias=True, exclude_none=True)})
    content = _edited_content(payload, parent)
    return _create_version(db, question, owner_id, request_id, fingerprint, parent["_id"], content)


def restore_version(
    db: Database, question: dict, owner_id: ObjectId,
    source_version_id: str, request_id: str,
) -> tuple[dict, bool]:
    source = committed_version(db, question, source_version_id)
    fingerprint = _fingerprint({"operation": "restore", "sourceVersionId": str(source["_id"])})
    content = {key: source[key] for key in ("type", "title", "required", "options", "validation")}
    return _create_version(db, question, owner_id, request_id, fingerprint, source["_id"], content)


def create_bank(db: Database, owner_id: ObjectId, payload: QuestionBankInput, request_id: str) -> tuple[dict, bool]:
    fingerprint = _fingerprint({"name": payload.name})
    bank = db.questionBanks.find_one({"ownerId": owner_id, "creationRequestId": request_id})
    if bank:
        if bank["creationFingerprint"] != fingerprint:
            raise _conflict("重复请求标识已用于不同题库")
        return bank, True
    now = _now()
    bank = {
        "ownerId": owner_id, "name": payload.name,
        "creationRequestId": request_id, "creationFingerprint": fingerprint,
        "createdAt": now, "updatedAt": now, "schemaVersion": 2,
    }
    try:
        bank["_id"] = db.questionBanks.insert_one(bank).inserted_id
        return bank, False
    except DuplicateKeyError:
        saved = db.questionBanks.find_one({"ownerId": owner_id, "creationRequestId": request_id})
        if saved is None or saved["creationFingerprint"] != fingerprint:
            raise _conflict("题库创建请求冲突") from None
        return saved, True


def rename_bank(db: Database, bank_id: str, owner_id: ObjectId, payload: QuestionBankInput) -> dict:
    bank = owned_bank(db, bank_id, owner_id)
    now = _now()
    result = db.questionBanks.update_one(
        {"_id": bank["_id"], "ownerId": owner_id, "deletedAt": None},
        {"$set": {"name": payload.name, "updatedAt": now}},
    )
    if result.matched_count != 1:
        raise _conflict("题库状态已变化，请刷新后重试")
    bank["name"] = payload.name
    bank["updatedAt"] = now
    return bank


def delete_bank(db: Database, bank_id: str, owner_id: ObjectId) -> None:
    bank = owned_bank(db, bank_id, owner_id)
    now = _now()
    result = db.questionBanks.update_one(
        {"_id": bank["_id"], "ownerId": owner_id, "deletedAt": None},
        {"$set": {"deletedAt": now, "updatedAt": now}},
    )
    if result.matched_count != 1:
        raise _conflict("题库状态已变化，请刷新后重试")


def add_bank_item(
    db: Database, bank: dict, question: dict, version: dict,
) -> tuple[dict, bool]:
    now = _now()
    item = {
        "bankId": bank["_id"], "libraryQuestionId": question["_id"],
        "selectedVersionId": version["_id"], "createdAt": now,
        "updatedAt": now, "schemaVersion": 2,
    }
    try:
        item["_id"] = db.questionBankItems.insert_one(item).inserted_id
        return item, False
    except DuplicateKeyError:
        saved = db.questionBankItems.find_one({"bankId": bank["_id"], "libraryQuestionId": question["_id"]})
        if saved is None or saved["selectedVersionId"] != version["_id"]:
            raise _conflict("题目已在题库中；切换版本请使用版本更新接口") from None
        return saved, True


def switch_bank_item_version(
    db: Database, bank: dict, question: dict, expected_id: ObjectId, selected_id: ObjectId,
) -> dict:
    item = db.questionBankItems.find_one({"bankId": bank["_id"], "libraryQuestionId": question["_id"]})
    if item is None:
        raise HTTPException(status_code=404, detail="题库条目不存在")
    if item["selectedVersionId"] == selected_id:
        return item
    if item["selectedVersionId"] != expected_id:
        raise _conflict("题库条目所选版本已变化，请重新读取")
    result = db.questionBankItems.update_one({"_id": item["_id"], "selectedVersionId": expected_id}, {
        "$set": {"selectedVersionId": selected_id, "updatedAt": _now()},
    })
    latest = db.questionBankItems.find_one({"_id": item["_id"]})
    if result.matched_count != 1 and (latest is None or latest["selectedVersionId"] != selected_id):
        raise _conflict("题库条目所选版本已变化，请重新读取")
    return latest
