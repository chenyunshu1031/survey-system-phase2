"""Authenticated personal question banks and immutable version history."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pymongo.database import Database

from app.db import get_db
from app.library_models import BankItemInput, BankItemVersionInput, LibraryVersionInput, QuestionBankInput, ShareInput
from app.models import QuestionInput
from app.security import current_user
from app.services.library import (
    add_bank_item, bank_item_view, bank_view, committed_version,
    create_bank, create_library_question, create_version, delete_bank, library_question_view,
    owned_bank, owned_library_question, restore_version, switch_bank_item_version,
    rename_bank, version_view,
)
from app.services.surveys import parse_object_id
from app.services.sharing import (
    accessible_library_question, grant_share, list_usages, revoke_share, share_view,
)


banks_router = APIRouter(prefix="/api/v1/question-banks", tags=["question banks"])
questions_router = APIRouter(prefix="/api/v1/library/questions", tags=["question library"])
shared_router = APIRouter(prefix="/api/v1/library/shared/questions", tags=["shared questions"])


def request_key(value: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if value is None or not 8 <= len(value) <= 100 or any(char.isspace() for char in value):
        raise HTTPException(status_code=422, detail="Idempotency-Key 须为 8–100 个无空白字符")
    return value


@banks_router.post("", status_code=status.HTTP_201_CREATED)
def post_bank(
    payload: QuestionBankInput, response: Response,
    user: dict = Depends(current_user), key: str = Depends(request_key),
    db: Database = Depends(get_db),
) -> dict:
    bank, replayed = create_bank(db, user["_id"], payload, key)
    if replayed:
        response.status_code = 200
    return bank_view(bank)


@banks_router.get("")
def list_banks(user: dict = Depends(current_user), db: Database = Depends(get_db)) -> list[dict]:
    return [bank_view(bank) for bank in db.questionBanks.find({"ownerId": user["_id"], "deletedAt": None}).sort("createdAt", -1)]


@banks_router.patch("/{bank_id}")
def patch_bank(
    bank_id: str, payload: QuestionBankInput,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    return bank_view(rename_bank(db, bank_id, user["_id"], payload))


@banks_router.delete("/{bank_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_bank(
    bank_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> None:
    delete_bank(db, bank_id, user["_id"])


@banks_router.get("/{bank_id}/items")
def list_bank_items(
    bank_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> list[dict]:
    bank = owned_bank(db, bank_id, user["_id"])
    items = []
    for item in db.questionBankItems.find({"bankId": bank["_id"]}).sort("createdAt", 1):
        question = db.libraryQuestions.find_one({"_id": item["libraryQuestionId"], "ownerId": user["_id"]})
        if question is None:
            continue
        try:
            committed_version(db, question, item["selectedVersionId"])
        except HTTPException:
            continue
        items.append(bank_item_view(db, item))
    return items


@banks_router.post("/{bank_id}/items", status_code=status.HTTP_201_CREATED)
def post_bank_item(
    bank_id: str, payload: BankItemInput, response: Response,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    bank = owned_bank(db, bank_id, user["_id"])
    question = owned_library_question(db, payload.library_question_id, user["_id"])
    version = committed_version(db, question, payload.selected_version_id)
    item, replayed = add_bank_item(db, bank, question, version)
    if replayed:
        response.status_code = 200
    return bank_item_view(db, item)


@banks_router.delete("/{bank_id}/items/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_item(
    bank_id: str, question_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> None:
    bank = owned_bank(db, bank_id, user["_id"])
    db.questionBankItems.delete_one({
        "bankId": bank["_id"], "libraryQuestionId": parse_object_id(question_id),
    })


@banks_router.put("/{bank_id}/items/{question_id}/version")
def put_bank_item_version(
    bank_id: str, question_id: str, payload: BankItemVersionInput,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    bank = owned_bank(db, bank_id, user["_id"])
    question = owned_library_question(db, question_id, user["_id"])
    selected = committed_version(db, question, payload.selected_version_id)
    expected_id = parse_object_id(payload.expected_version_id)
    item = switch_bank_item_version(db, bank, question, expected_id, selected["_id"])
    return bank_item_view(db, item)


@questions_router.post("", status_code=status.HTTP_201_CREATED)
def post_library_question(
    payload: QuestionInput, response: Response,
    user: dict = Depends(current_user), key: str = Depends(request_key),
    db: Database = Depends(get_db),
) -> dict:
    question, _, replayed = create_library_question(db, user["_id"], payload, key)
    if replayed:
        response.status_code = 200
    return library_question_view(db, question)


@questions_router.get("")
def list_library_questions(
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> list[dict]:
    questions = db.libraryQuestions.find({"ownerId": user["_id"]}).sort("createdAt", -1)
    return [library_question_view(db, question) for question in questions if question.get("currentVersionId")]


@questions_router.get("/{question_id}")
def get_library_question(
    question_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    question = accessible_library_question(db, question_id, user["_id"])
    return library_question_view(db, question)


@questions_router.get("/{question_id}/versions")
def list_versions(
    question_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> list[dict]:
    question = accessible_library_question(db, question_id, user["_id"])
    versions = db.questionVersions.find({
        "libraryQuestionId": question["_id"], "versionNo": {"$lte": question.get("versionCounter", 0)},
    }).sort("versionNo", 1)
    return [version_view(version) for version in versions]


@questions_router.post("/{question_id}/versions", status_code=status.HTTP_201_CREATED)
def post_version(
    question_id: str, payload: LibraryVersionInput, response: Response,
    user: dict = Depends(current_user), key: str = Depends(request_key),
    db: Database = Depends(get_db),
) -> dict:
    question = owned_library_question(db, question_id, user["_id"])
    version, replayed = create_version(db, question, user["_id"], payload, key)
    if replayed:
        response.status_code = 200
    return version_view(version)


@questions_router.post("/{question_id}/versions/{version_id}/restore", status_code=status.HTTP_201_CREATED)
def post_restore_version(
    question_id: str, version_id: str, response: Response,
    user: dict = Depends(current_user), key: str = Depends(request_key),
    db: Database = Depends(get_db),
) -> dict:
    question = owned_library_question(db, question_id, user["_id"])
    version, replayed = restore_version(db, question, user["_id"], version_id, key)
    if replayed:
        response.status_code = 200
    return version_view(version)


@questions_router.post("/{question_id}/shares", status_code=status.HTTP_201_CREATED)
def post_share(
    question_id: str, payload: ShareInput, response: Response,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> dict:
    recipient_id = payload.recipient_user_id
    if payload.recipient_username is not None:
        owned_library_question(db, question_id, user["_id"])
        recipient = db.users.find_one({"usernameKey": payload.recipient_username.casefold()}, {"_id": 1})
        if recipient is None:
            raise HTTPException(status_code=404, detail="接收用户不存在")
        recipient_id = str(recipient["_id"])
    assert recipient_id is not None
    share, replayed = grant_share(db, question_id, user["_id"], recipient_id)
    if replayed:
        response.status_code = 200
    return share_view(share, db)


@questions_router.get("/{question_id}/shares")
def get_shares(
    question_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> list[dict]:
    question = owned_library_question(db, question_id, user["_id"])
    shares = db.questionShares.find({"libraryQuestionId": question["_id"], "revokedAt": None})
    return [share_view(share, db) for share in shares]


@questions_router.delete("/{question_id}/shares/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_share(
    question_id: str, recipient_id: str,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> None:
    revoke_share(db, question_id, user["_id"], recipient_id)


@questions_router.get("/{question_id}/usages")
def get_usages(
    question_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> list[dict]:
    return list_usages(db, question_id, user["_id"])


@shared_router.get("")
def list_shared_questions(
    user: dict = Depends(current_user), db: Database = Depends(get_db),
) -> list[dict]:
    items = []
    shares = db.questionShares.find({"recipientUserId": user["_id"], "revokedAt": None})
    for share in shares:
        question = db.libraryQuestions.find_one({"_id": share["libraryQuestionId"]})
        if question and question.get("currentVersionId"):
            items.append(library_question_view(db, question))
    return items
