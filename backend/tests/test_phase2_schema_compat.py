"""Schema upgrade checks without opening the configured business database."""

from datetime import datetime, timezone

import mongomock
import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.db.schema import SCHEMAS, initialize_database
from app.routers.questions import list_questions


class IsolatedSchemaDatabase:
    """Use mongomock for indexes and record the MongoDB validator commands."""

    def __init__(self):
        self.store = mongomock.MongoClient().phase2_schema_test
        self.validators = {}
        self.modified_validators = []

    def __getattr__(self, name):
        return getattr(self.store, name)

    def list_collection_names(self):
        return self.store.list_collection_names()

    def create_collection(self, name, *, validator, validationLevel):
        assert validationLevel == "strict"
        self.validators[name] = validator
        return self.store.create_collection(name)

    def command(self, command):
        if command == "ping":
            return {"ok": 1}
        assert command["validationLevel"] == "strict"
        name = command["collMod"]
        self.validators[name] = command["validator"]
        self.modified_validators.append(name)
        return {"ok": 1}


def test_schema_initialization_is_repeatable_and_preserves_legacy_documents():
    db = IsolatedSchemaDatabase()
    survey_id, question_id, response_id = ObjectId(), ObjectId(), ObjectId()
    owner_id = ObjectId()
    now = datetime.now(timezone.utc)
    db.surveys.insert_one({
        "_id": survey_id, "ownerId": owner_id, "slug": "legacy", "title": "旧问卷",
        "description": "", "allowAnonymous": False, "allowMultipleSubmissions": False,
        "status": "published", "activeQuestionMutations": 2, "activeSubmissions": 3,
        "createdAt": now, "updatedAt": now, "schemaVersion": 1,
    })
    old_question = {
        "_id": question_id, "surveyId": survey_id, "order": 1, "type": "text",
        "title": "旧题目", "required": False, "options": [], "validation": {},
        "jumpRules": [], "schemaVersion": 1,
    }
    db.questions.insert_one(old_question.copy())
    old_response = {
        "_id": response_id, "surveyId": survey_id, "respondentId": owner_id,
        "isAnonymous": False, "answers": [{"questionId": str(question_id), "value": "旧答案"}],
        "visitedQuestionIds": [str(question_id)], "submittedAt": now,
        "singleSubmission": True, "schemaVersion": 1,
    }
    db.responses.insert_one(old_response.copy())
    stored_response_before = db.responses.find_one({"_id": response_id})
    share_id = ObjectId()
    db.questionShares.insert_one({
        "_id": share_id, "libraryQuestionId": ObjectId(), "recipientUserId": owner_id,
        "grantedById": ObjectId(), "createdAt": now, "activeSelections": 2,
        "schemaVersion": 2,
    })

    initialize_database(db)
    initialize_database(db)

    assert set(db.list_collection_names()) == set(SCHEMAS)
    assert set(db.modified_validators) == set(SCHEMAS)
    assert db.questions.find_one({"_id": question_id}) == old_question
    assert db.responses.find_one({"_id": response_id}) == stored_response_before
    saved_survey = db.surveys.find_one({"_id": survey_id})
    assert saved_survey["activeQuestionMutations"] == saved_survey["activeSubmissions"] == 0
    assert "configurationRevision" not in saved_survey
    assert "submissionRevision" not in saved_survey
    assert db.questions.count_documents({}) == db.responses.count_documents({}) == 1
    assert db.questionShares.find_one({"_id": share_id})["activeSelections"] == 0


def test_new_validators_keep_question_sources_optional_and_typed():
    db = IsolatedSchemaDatabase()
    initialize_database(db)

    question_schema = db.validators["questions"]["$jsonSchema"]
    for name in ("sourceLibraryQuestionId", "sourceVersionId"):
        assert name not in question_schema["required"]
        assert question_schema["properties"][name] == {"bsonType": "objectId"}
    assert SCHEMAS["questions"]["required"] == [
        "surveyId", "order", "type", "title", "required", "options",
        "validation", "jumpRules", "schemaVersion",
    ]
    for name in ("libraryQuestions", "questionVersions", "questionBanks", "questionBankItems", "questionShares"):
        assert db.validators[name]["$jsonSchema"]["required"] == SCHEMAS[name]["required"]
    assert SCHEMAS["questionVersions"]["properties"]["options"] == SCHEMAS["questions"]["properties"]["options"]
    assert SCHEMAS["questionVersions"]["properties"]["validation"] == SCHEMAS["questions"]["properties"]["validation"]


def test_new_indexes_enforce_identity_and_support_lookup():
    db = IsolatedSchemaDatabase()
    initialize_database(db)

    usage = db.questions.index_information()["source_question_usages"]
    assert usage["key"] == [
        ("sourceLibraryQuestionId", 1), ("sourceVersionId", 1), ("surveyId", 1),
    ]
    assert usage["partialFilterExpression"] == {"sourceLibraryQuestionId": {"$exists": True}}
    assert db.libraryQuestions.index_information()["owner_library_questions"]["key"] == [
        ("ownerId", 1), ("createdAt", -1), ("_id", -1),
    ]
    assert db.questionBanks.index_information()["owner_question_banks"]["key"] == [
        ("ownerId", 1), ("createdAt", -1), ("_id", -1),
    ]
    assert db.questionVersions.index_information()["version_children"]["key"] == [("parentVersionId", 1)]
    assert db.questionShares.index_information()["recipient_shared_questions"]["key"] == [
        ("recipientUserId", 1), ("libraryQuestionId", 1),
    ]

    for collection, fields in (
        (db.questionVersions, {"libraryQuestionId": ObjectId(), "versionNo": 1}),
        (db.questionBankItems, {"bankId": ObjectId(), "libraryQuestionId": ObjectId()}),
        (db.questionShares, {"libraryQuestionId": ObjectId(), "recipientUserId": ObjectId()}),
    ):
        collection.insert_one(fields.copy())
        with pytest.raises(DuplicateKeyError):
            collection.insert_one(fields.copy())


def test_old_question_read_shape_is_unchanged_when_source_metadata_exists():
    db = mongomock.MongoClient().phase2_question_read_test
    owner_id, survey_id, question_id = ObjectId(), ObjectId(), ObjectId()
    db.surveys.insert_one({"_id": survey_id, "ownerId": owner_id})
    db.questions.insert_one({
        "_id": question_id, "surveyId": survey_id, "order": 1, "type": "text",
        "title": "旧题目", "required": False, "options": [], "validation": {},
        "jumpRules": [], "schemaVersion": 1,
    })
    original = list_questions(str(survey_id), {"_id": owner_id}, db)
    assert len(original) == 1
    assert "sourceVersionId" not in original[0]
    assert "sourceLibraryQuestionId" not in original[0]

    db.questions.update_one({"_id": question_id}, {"$set": {
        "sourceLibraryQuestionId": ObjectId(), "sourceVersionId": ObjectId(),
    }})
    sourced = list_questions(str(survey_id), {"_id": owner_id}, db)[0]
    assert {key: value for key, value in sourced.items() if key not in {"sourceLibraryQuestionId", "sourceVersionId"}} == original[0]
    assert sourced["sourceLibraryQuestionId"] and sourced["sourceVersionId"]
