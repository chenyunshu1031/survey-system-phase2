"""Opt-in schema check on an explicitly isolated MongoDB instance."""

import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, WriteError

from app.db.schema import initialize_database


@pytest.mark.skipif(os.getenv("RUN_LIBRARY_MONGO_INTEGRATION") != "1", reason="requires isolated MongoDB URI")
def test_cross_survey_consent_schema_on_isolated_mongodb():
    uri = os.getenv("LIBRARY_MONGO_TEST_URI")
    assert uri, "LIBRARY_MONGO_TEST_URI must name an isolated test instance"
    parsed = urlparse(uri)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port not in {None, 27017}
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    name = f"survey_system_cross_statistics_{uuid4().hex}"
    db = client[name]
    try:
        assert client.admin.command("buildInfo")["version"] == "8.3.11"
        initialize_database(db)
        initialize_database(db)
        assert "crossSurveyConsents" in db.list_collection_names()
        with pytest.raises(WriteError):
            db.crossSurveyConsents.insert_one({"invalid": True})
        now = datetime.now(timezone.utc)
        consent = {
            "surveyId": ObjectId(), "libraryQuestionId": ObjectId(), "grantedById": ObjectId(),
            "revision": 1, "createdAt": now, "updatedAt": now, "schemaVersion": 2,
        }
        db.crossSurveyConsents.insert_one(consent.copy())
        with pytest.raises(DuplicateKeyError):
            db.crossSurveyConsents.insert_one(consent.copy())
        assert db.crossSurveyConsents.index_information()["active_library_consents"]["key"] == [
            ("libraryQuestionId", 1), ("revokedAt", 1), ("surveyId", 1),
        ]
    finally:
        client.drop_database(name)
        client.close()
