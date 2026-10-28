"""Opt-in library smoke test; never defaults to the business MongoDB port."""

import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pymongo import MongoClient
from pymongo.errors import WriteError

from app.db.schema import initialize_database
from app.library_models import LibraryVersionInput, QuestionBankInput
from app.models import QuestionInput
from app.services.library import (
    add_bank_item, create_bank, create_library_question, create_version,
    delete_bank, owned_bank, owned_library_question, rename_bank, restore_version, switch_bank_item_version,
)
from app.services.sharing import grant_share, reserve_shared_selection, revoke_share, version_snapshot


@pytest.mark.skipif(os.getenv("RUN_LIBRARY_MONGO_INTEGRATION") != "1", reason="requires an explicit isolated MongoDB URI")
def test_library_schema_and_write_flow_on_isolated_mongodb():
    uri = os.getenv("LIBRARY_MONGO_TEST_URI")
    assert uri, "LIBRARY_MONGO_TEST_URI must name an isolated test instance"
    parsed = urlparse(uri)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port not in {None, 27017}
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    name = f"survey_system_library_test_{uuid4().hex}"
    db = client[name]
    try:
        assert client.admin.command("buildInfo")["version"] == "8.3.11"
        initialize_database(db)
        initialize_database(db)
        for collection in ("libraryQuestions", "questionVersions", "questionBanks", "questionBankItems"):
            assert collection in db.list_collection_names()
            with pytest.raises(WriteError):
                db[collection].insert_one({"invalid": True})

        from bson import ObjectId

        owner_id = ObjectId()
        payload = QuestionInput(type="single", title="题库年龄题", options=["甲", "乙"])
        logical, first, replayed = create_library_question(db, owner_id, payload, "real-create-001")
        assert not replayed and first["versionNo"] == 1
        repeated, repeated_first, replayed = create_library_question(db, owner_id, payload, "real-create-001")
        assert replayed and repeated["_id"] == logical["_id"] and repeated_first["_id"] == first["_id"]

        edited = LibraryVersionInput.model_validate({
            "parentVersionId": str(first["_id"]), "type": "single", "title": "新版年龄题",
            "options": [{"id": first["options"][0]["id"], "label": "甲"}, {"label": "丙"}],
        })
        second, replayed = create_version(db, logical, owner_id, edited, "real-version-002")
        assert not replayed and second["versionNo"] == 2
        latest = owned_library_question(db, str(logical["_id"]), owner_id)
        restored, replayed = restore_version(db, latest, owner_id, str(first["_id"]), "real-restore-003")
        assert not replayed and restored["versionNo"] == 3 and restored["parentVersionId"] == first["_id"]
        assert db.questionVersions.find_one({"_id": first["_id"]})["title"] == "题库年龄题"

        bank, _ = create_bank(db, owner_id, QuestionBankInput(name="个人题库"), "real-bank-001")
        item, _ = add_bank_item(db, bank, latest, first)
        assert item["selectedVersionId"] == first["_id"]
        item = switch_bank_item_version(db, bank, latest, first["_id"], restored["_id"])
        assert item["selectedVersionId"] == restored["_id"]
        assert rename_bank(db, str(bank["_id"]), owner_id, QuestionBankInput(name="新版题库"))["name"] == "新版题库"
        delete_bank(db, str(bank["_id"]), owner_id)
        assert db.questionBanks.find_one({"_id": bank["_id"]})["deletedAt"] is not None
        assert db.questionBankItems.find_one({"_id": item["_id"]}) is not None
        with pytest.raises(HTTPException) as deleted_bank:
            owned_bank(db, str(bank["_id"]), owner_id)
        assert deleted_bank.value.status_code == 404
        recipient_id = ObjectId()
        db.users.insert_one({
            "_id": recipient_id, "username": "isolated_recipient", "usernameKey": "isolated_recipient",
            "passwordHash": "test-only", "createdAt": datetime.now(timezone.utc), "schemaVersion": 1,
        })
        share, replayed = grant_share(db, str(logical["_id"]), owner_id, str(recipient_id))
        assert not replayed and share["activeSelections"] == 0
        with reserve_shared_selection(db, latest, recipient_id):
            with pytest.raises(HTTPException) as conflict:
                revoke_share(db, str(logical["_id"]), owner_id, str(recipient_id))
            assert conflict.value.status_code == 409
        revoke_share(db, str(logical["_id"]), owner_id, str(recipient_id))
        with pytest.raises(HTTPException) as revoked:
            with reserve_shared_selection(db, latest, recipient_id):
                pass
        assert revoked.value.status_code == 404

        survey_id = ObjectId()
        sourced = version_snapshot(survey_id, 1, latest, first)
        db.questions.insert_one(sourced)
        assert db.questions.find_one({"_id": sourced["_id"]})["sourceVersionId"] == first["_id"]
        unpaired = version_snapshot(survey_id, 2, latest, first)
        del unpaired["sourceVersionId"]
        with pytest.raises(WriteError):
            db.questions.insert_one(unpaired)
        imported, _, _ = create_library_question(
            db, owner_id, payload, "real-import-001",
            source_survey_id=survey_id, source_question_id=ObjectId(),
        )
        assert imported["importedFromQuestionId"] is not None
        with pytest.raises(HTTPException) as duplicate_import:
            create_library_question(
                db, owner_id, payload, "real-import-002",
                source_survey_id=survey_id,
                source_question_id=imported["importedFromQuestionId"],
            )
        assert duplicate_import.value.status_code == 409
        assert db.libraryQuestions.count_documents({}) == 2
        assert db.questionVersions.count_documents({}) == 4
    finally:
        client.drop_database(name)
        client.close()
