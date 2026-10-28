from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.library_models import SurveyLibraryQuestionInput
from app.routers.questions import add_question_from_library
from app.services import sharing as sharing_service
from conftest import register_and_login


@pytest.fixture(autouse=True)
def share_index(db):
    db.questionShares.create_index([("libraryQuestionId", 1), ("recipientUserId", 1)], unique=True)


def account(client, db, name):
    headers = register_and_login(client, name)
    user = db.users.find_one({"username": name})
    return headers, user


def library_question(client, headers, key="share-library-001"):
    created = client.post("/api/v1/library/questions", headers={**headers, "Idempotency-Key": key}, json={
        "type": "single", "title": "共享选择题", "required": True,
        "options": ["甲", "乙"],
    })
    assert created.status_code == 201, created.text
    return created.json()


def survey(client, headers, title="个人问卷"):
    result = client.post("/api/v1/surveys", headers=headers, json={"title": title})
    assert result.status_code == 201, result.text
    return result.json()


def grant(client, owner_headers, question_id, recipient_id):
    return client.post(f"/api/v1/library/questions/{question_id}/shares", headers=owner_headers,
                       json={"recipientUserId": str(recipient_id)})


def select(client, headers, survey_id, logical_id, version_id):
    return client.post(f"/api/v1/surveys/{survey_id}/questions/from-library", headers=headers,
                       json={"libraryQuestionId": logical_id, "versionId": version_id})


def test_share_grant_read_and_owner_only_writes(client, db):
    owner, owner_user = account(client, db, "share_owner")
    recipient, recipient_user = account(client, db, "share_recipient")
    stranger, stranger_user = account(client, db, "share_stranger")
    logical = library_question(client, owner)
    question_id = logical["id"]
    base = f"/api/v1/library/questions/{question_id}"
    assert client.get(base, headers=recipient).status_code == 404
    assert grant(client, recipient, question_id, stranger_user["_id"]).status_code == 404
    assert grant(client, owner, question_id, owner_user["_id"]).status_code == 422
    assert grant(client, owner, question_id, ObjectId()).status_code == 404
    created = grant(client, owner, question_id, recipient_user["_id"])
    assert created.status_code == 201, created.text
    repeated = grant(client, owner, question_id, recipient_user["_id"])
    assert repeated.status_code == 200
    assert len(client.get(f"{base}/shares", headers=owner).json()) == 1
    assert client.get(f"{base}/shares", headers=recipient).status_code == 404
    assert client.get(base, headers=recipient).json()["id"] == question_id
    versions = client.get(f"{base}/versions", headers=recipient).json()
    assert len(versions) == 1 and versions[0]["id"] == logical["currentVersionId"]
    shared = client.get("/api/v1/library/shared/questions", headers=recipient).json()
    assert [item["id"] for item in shared] == [question_id]
    assert client.get(base, headers=stranger).status_code == 404
    assert client.get(f"{base}/versions", headers=stranger).status_code == 404
    assert client.post(f"{base}/versions", headers={**recipient, "Idempotency-Key": "not-owner-edit"}, json={
        "parentVersionId": versions[0]["id"], "type": "text", "title": "无权改版",
    }).status_code == 404
    assert client.post(f"{base}/versions/{versions[0]['id']}/restore",
                       headers={**recipient, "Idempotency-Key": "not-owner-restore"}).status_code == 404
    bank = client.post("/api/v1/question-banks", headers={**owner, "Idempotency-Key": "share-owner-bank"},
                       json={"name": "所有者题库"}).json()
    assert client.get(f"/api/v1/question-banks/{bank['id']}/items", headers=recipient).status_code == 404


def test_each_selection_copies_committed_version_and_revoke_preserves_snapshot(client, db):
    owner, owner_user = account(client, db, "snapshot_owner")
    recipient, recipient_user = account(client, db, "snapshot_recipient")
    logical = library_question(client, owner)
    first = logical["currentVersion"]
    first_id = first["id"]
    assert grant(client, owner, logical["id"], recipient_user["_id"]).status_code == 201
    draft = survey(client, recipient)
    first_selection = select(client, recipient, draft["id"], logical["id"], first_id)
    second_selection = select(client, recipient, draft["id"], logical["id"], first_id)
    assert first_selection.status_code == second_selection.status_code == 201
    first_instance, second_instance = first_selection.json(), second_selection.json()
    assert first_instance["id"] != second_instance["id"]
    assert [first_instance["order"], second_instance["order"]] == [1, 2]
    saved = db.questions.find_one({"_id": ObjectId(first_instance["id"])})
    assert saved["surveyId"] == ObjectId(draft["id"])
    assert saved["sourceLibraryQuestionId"] == ObjectId(logical["id"])
    assert saved["sourceVersionId"] == ObjectId(first_id)
    for field in ("type", "title", "required", "options", "validation"):
        assert saved[field] == first[field]
    assert saved["jumpRules"] == []
    assert first_instance["sourceVersionId"] == first_id  # owner-only source metadata
    assert db.questionVersions.find_one({"_id": ObjectId(first_id)})["title"] == first["title"]

    revoke_url = f"/api/v1/library/questions/{logical['id']}/shares/{recipient_user['_id']}"
    assert client.delete(revoke_url, headers=owner).status_code == 204
    assert client.get(f"/api/v1/library/questions/{logical['id']}", headers=recipient).status_code == 404
    assert select(client, recipient, draft["id"], logical["id"], first_id).status_code == 404
    assert db.questions.count_documents({"surveyId": ObjectId(draft["id"])}) == 2
    assert db.questions.find_one({"_id": ObjectId(first_instance["id"])}) == saved
    assert len(client.get(f"/api/v1/library/questions/{logical['id']}/usages", headers=owner).json()) == 2
    assert client.post(f"/api/v1/surveys/{draft['id']}/publish", headers=recipient).status_code == 200
    assert client.delete(revoke_url, headers=owner).status_code == 204
    assert grant(client, owner, logical["id"], recipient_user["_id"]).status_code == 201
    assert select(client, recipient, draft["id"], logical["id"], first_id).status_code == 409
    assert client.get(f"/api/v1/surveys/{draft['id']}/questions", headers=recipient).status_code == 200


def test_version_must_belong_to_logical_question_and_be_committed(client, db):
    owner, _ = account(client, db, "version_match_owner")
    first = library_question(client, owner)
    second = library_question(client, owner, key="share-library-002")
    draft = survey(client, owner)
    mismatch = select(client, owner, draft["id"], first["id"], second["currentVersionId"])
    assert mismatch.status_code == 404
    pending_id = ObjectId()
    db.questionVersions.insert_one({
        "_id": pending_id, "libraryQuestionId": ObjectId(first["id"]), "versionNo": 2,
        "type": "text", "title": "尚未提交", "required": False, "options": [], "validation": {},
    })
    assert select(client, owner, draft["id"], first["id"], str(pending_id)).status_code == 404
    assert db.questions.count_documents({"surveyId": ObjectId(draft["id"])}) == 0


@pytest.mark.parametrize("changed", ["title", "type", "required", "options", "validation"])
def test_editing_content_detaches_both_source_ids(client, db, changed):
    owner, _ = account(client, db, f"detach_{changed}")
    logical = library_question(client, owner)
    draft = survey(client, owner)
    instance = select(client, owner, draft["id"], logical["id"], logical["currentVersionId"]).json()
    payload = {
        "type": "single", "title": instance["title"], "required": instance["required"],
        "options": [{"id": option["id"], "label": option["label"]} for option in instance["options"]],
        "validation": {},
    }
    if changed == "title":
        payload["title"] = "题干已修改"
    elif changed == "type":
        payload.update({"type": "text", "options": []})
    elif changed == "required":
        payload["required"] = False
    elif changed == "options":
        payload["options"][0]["label"] = "新选项文字"
    else:
        payload.update({"type": "multiple", "validation": {"minSelections": 1}})
    result = client.put(f"/api/v1/surveys/{draft['id']}/questions/{instance['id']}",
                        headers=owner, json=payload)
    assert result.status_code == 200, result.text
    saved = db.questions.find_one({"_id": ObjectId(instance["id"])})
    assert "sourceLibraryQuestionId" not in saved and "sourceVersionId" not in saved
    assert client.get(f"/api/v1/library/questions/{logical['id']}/usages", headers=owner).json() == []


def test_only_jump_rules_change_keeps_source_and_malformed_source_cannot_publish(client, db):
    owner, _ = account(client, db, "rule_source_owner")
    logical = library_question(client, owner)
    draft = survey(client, owner)
    instance = select(client, owner, draft["id"], logical["id"], logical["currentVersionId"]).json()
    target = client.post(f"/api/v1/surveys/{draft['id']}/questions", headers=owner,
                         json={"type": "text", "title": "目标题"}).json()
    rules = [{"priority": 1, "operator": "equals", "optionIds": [instance["options"][0]["id"]],
              "targetQuestionId": target["id"]}]
    saved_rules = client.put(f"/api/v1/surveys/{draft['id']}/questions/{instance['id']}/jump-rules",
                             headers=owner, json={"rules": rules})
    assert saved_rules.status_code == 200, saved_rules.text
    source = db.questions.find_one({"_id": ObjectId(instance["id"])})
    assert source["sourceLibraryQuestionId"] == ObjectId(logical["id"])
    assert source["sourceVersionId"] == ObjectId(logical["currentVersionId"])
    assert client.post(f"/api/v1/surveys/{draft['id']}/publish", headers=owner).status_code == 200
    assert client.put(f"/api/v1/surveys/{draft['id']}/questions/{instance['id']}", headers=owner,
                      json={"type": "single", "title": "发布后改题", "options": [
                          {"id": option["id"], "label": option["label"]} for option in instance["options"]
                      ]}).status_code == 409

    another = survey(client, owner, "校验来源")
    other_instance = select(client, owner, another["id"], logical["id"], logical["currentVersionId"]).json()
    db.questions.update_one({"_id": ObjectId(other_instance["id"])}, {"$unset": {"sourceVersionId": ""}})
    assert client.post(f"/api/v1/surveys/{another['id']}/publish", headers=owner).status_code == 409


def test_usage_traces_minimal_fields_and_statuses(client, db):
    owner, owner_user = account(client, db, "usage_owner")
    recipient, recipient_user = account(client, db, "usage_recipient")
    logical = library_question(client, owner)
    assert grant(client, owner, logical["id"], recipient_user["_id"]).status_code == 201
    own_survey = survey(client, owner, "自己的私有标题")
    shared_survey = survey(client, recipient, "他人的私有标题")
    own_instance = select(client, owner, own_survey["id"], logical["id"], logical["currentVersionId"]).json()
    shared_instance = select(client, recipient, shared_survey["id"], logical["id"], logical["currentVersionId"]).json()
    usages_url = f"/api/v1/library/questions/{logical['id']}/usages"
    assert client.get(usages_url, headers=recipient).status_code == 404
    initial = client.get(usages_url, headers=owner).json()
    assert len(initial) == 2
    assert {item["status"] for item in initial} == {"draft"}
    assert {item["questionId"] for item in initial} == {own_instance["id"], shared_instance["id"]}
    assert {item["versionId"] for item in initial} == {logical["currentVersionId"]}
    assert all(set(item) == {"surveyId", "questionId", "versionId", "status", "isOwnSurvey"} for item in initial)
    assert sum(item["isOwnSurvey"] for item in initial) == 1
    assert client.post(f"/api/v1/surveys/{own_survey['id']}/publish", headers=owner).status_code == 200
    assert client.post(f"/api/v1/surveys/{shared_survey['id']}/publish", headers=recipient).status_code == 200
    assert client.post(f"/api/v1/surveys/{shared_survey['id']}/close", headers=recipient).status_code == 200
    final = client.get(usages_url, headers=owner).json()
    assert {item["status"] for item in final} == {"published", "closed"}
    assert "他人的私有标题" not in str(final)
    assert str(recipient_user["_id"]) not in str(final)


def test_revoke_conflicts_with_in_flight_selection_and_publish_is_fenced(client, db, monkeypatch):
    owner, _ = account(client, db, "race_owner")
    recipient, recipient_user = account(client, db, "race_recipient")
    logical = library_question(client, owner)
    draft = survey(client, recipient)
    seed = client.post(f"/api/v1/surveys/{draft['id']}/questions", headers=recipient,
                       json={"type": "text", "title": "原有题目"})
    assert seed.status_code == 201
    assert grant(client, owner, logical["id"], recipient_user["_id"]).status_code == 201
    entered, release = Event(), Event()
    original_snapshot = sharing_service.version_snapshot
    from app.routers import questions as question_router

    def paused_snapshot(*args):
        entered.set()
        assert release.wait(5)
        return original_snapshot(*args)

    monkeypatch.setattr(question_router, "version_snapshot", paused_snapshot)
    logical_id = logical["id"]
    payload = SurveyLibraryQuestionInput(library_question_id=logical_id, version_id=logical["currentVersionId"])
    with ThreadPoolExecutor(max_workers=2) as workers:
        future = workers.submit(add_question_from_library, draft["id"], payload, recipient_user, db)
        assert entered.wait(5)
        with pytest.raises(HTTPException) as error:
            sharing_service.revoke_share(db, logical_id, db.users.find_one({"username": "race_owner"})["_id"], str(recipient_user["_id"]))
        assert error.value.status_code == 409
        with pytest.raises(HTTPException) as concurrent:
            add_question_from_library(draft["id"], payload, recipient_user, db)
        assert concurrent.value.status_code == 409
        assert client.post(f"/api/v1/surveys/{draft['id']}/publish", headers=recipient).status_code == 409
        release.set()
        inserted = future.result(timeout=5)
    assert inserted["order"] == 2
    assert client.delete(f"/api/v1/library/questions/{logical_id}/shares/{recipient_user['_id']}", headers=owner).status_code == 204
    assert db.questionShares.find_one({"libraryQuestionId": ObjectId(logical_id)})["activeSelections"] == 0
