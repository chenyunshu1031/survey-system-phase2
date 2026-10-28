from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.library_models import LibraryVersionInput
from app.services import library as library_service
from conftest import register_and_login


@pytest.fixture(autouse=True)
def library_indexes(db):
    # API tests use mongomock, so install the unique indexes used by production.
    db.libraryQuestions.create_index([("ownerId", 1), ("creationRequestId", 1)], unique=True)
    db.questionVersions.create_index([("libraryQuestionId", 1), ("versionNo", 1)], unique=True)
    db.questionVersions.create_index([("libraryQuestionId", 1), ("requestId", 1)], unique=True)
    db.questionBanks.create_index([("ownerId", 1), ("creationRequestId", 1)], unique=True)
    db.questionBankItems.create_index([("bankId", 1), ("libraryQuestionId", 1)], unique=True)


def with_key(headers, key):
    return {**headers, "Idempotency-Key": key}


def make_question(client, owner, key="library-create-001", title="常用题"):
    result = client.post("/api/v1/library/questions", headers=with_key(owner, key), json={
        "type": "single", "title": title, "required": True,
        "options": ["甲", "乙"],
    })
    assert result.status_code == 201, result.text
    return result.json()


def make_bank(client, owner, key="bank-create-001", name="我的题库"):
    result = client.post("/api/v1/question-banks", headers=with_key(owner, key), json={"name": name})
    assert result.status_code == 201, result.text
    return result.json()


def version_payload(first, *, title="新版题目"):
    return {
        "parentVersionId": first["id"], "type": "single", "title": title,
        "required": True,
        "options": [
            {"id": first["options"][0]["id"], "label": "甲（新版）"},
            {"label": "丙"},
        ],
        "validation": {},
    }


def test_personal_banks_are_listed_and_create_retries_are_idempotent(client, db):
    owner = register_and_login(client, "bank_owner")
    other = register_and_login(client, "bank_other")
    url = "/api/v1/question-banks"
    assert client.post(url, json={"name": "匿名请求"}).status_code == 401
    assert client.post(url, headers=owner, json={"name": "缺少请求标识"}).status_code == 422
    created = make_bank(client, owner)
    replay = client.post(url, headers=with_key(owner, "bank-create-001"), json={"name": " 我的题库 "})
    assert replay.status_code == 200 and replay.json()["id"] == created["id"]
    assert client.post(url, headers=with_key(owner, "bank-create-001"), json={"name": "其他名称"}).status_code == 409
    assert [item["id"] for item in client.get(url, headers=owner).json()] == [created["id"]]
    assert client.get(url, headers=other).json() == []
    assert client.get(f"{url}/{created['id']}/items", headers=other).status_code == 404
    assert db.questionBanks.count_documents({}) == 1


def test_bank_can_be_renamed_and_removed_without_deleting_questions(client, db):
    owner = register_and_login(client, "bank_manage_owner")
    other = register_and_login(client, "bank_manage_other")
    bank = make_bank(client, owner)
    question = make_question(client, owner)
    base = f"/api/v1/question-banks/{bank['id']}"
    item = client.post(f"{base}/items", headers=owner, json={
        "libraryQuestionId": question["id"], "selectedVersionId": question["currentVersionId"],
    })
    assert item.status_code == 201
    assert client.patch(base, headers=other, json={"name": "越权"}).status_code == 404
    assert client.delete(base, headers=other).status_code == 404
    assert client.patch(base, headers=owner, json={"name": "   "}).status_code == 422
    renamed = client.patch(base, headers=owner, json={"name": " 常用问卷题 "})
    assert renamed.status_code == 200 and renamed.json()["name"] == "常用问卷题"
    assert client.get("/api/v1/question-banks", headers=owner).json()[0]["name"] == "常用问卷题"
    assert client.delete(base, headers=owner).status_code == 204
    assert client.get("/api/v1/question-banks", headers=owner).json() == []
    assert client.get(f"{base}/items", headers=owner).status_code == 404
    assert client.post(f"{base}/items", headers=owner, json={
        "libraryQuestionId": question["id"], "selectedVersionId": question["currentVersionId"],
    }).status_code == 404
    assert client.get(f"/api/v1/library/questions/{question['id']}", headers=owner).status_code == 200
    assert db.questionVersions.count_documents({"libraryQuestionId": ObjectId(question["id"])}) == 1
    assert db.questionBankItems.count_documents({"bankId": ObjectId(bank["id"])}) == 1
    assert db.questionBanks.find_one({"_id": ObjectId(bank["id"])})["deletedAt"] is not None


def test_old_survey_question_can_be_saved_for_future_reuse_without_rewriting_original(client, db):
    owner = register_and_login(client, "import_old_question_owner")
    other = register_and_login(client, "import_old_question_other")
    old_survey = client.post("/api/v1/surveys", headers=owner, json={"title": "旧问卷"}).json()
    old_item = client.post(f"/api/v1/surveys/{old_survey['id']}/questions", headers=owner, json={
        "type": "number", "title": "年龄", "required": True,
        "validation": {"minValue": 0, "maxValue": 120, "integerOnly": True},
    }).json()
    assert client.post(f"/api/v1/surveys/{old_survey['id']}/publish", headers=owner).status_code == 200
    original = deepcopy(db.questions.find_one({"_id": ObjectId(old_item["id"])}))
    url = f"/api/v1/surveys/{old_survey['id']}/questions/{old_item['id']}/save-to-library"
    assert client.post(url, headers=with_key(other, "import-old-question")).status_code == 404
    imported = client.post(url, headers=with_key(owner, "import-old-question"))
    assert imported.status_code == 201, imported.text
    assert imported.json()["currentVersion"]["title"] == "年龄"
    assert imported.json()["currentVersion"]["validation"]["maxValue"] == 120
    assert client.post(url, headers=with_key(owner, "import-old-question")).json()["id"] == imported.json()["id"]
    assert client.post(url, headers=with_key(owner, "import-old-question-again")).status_code == 409
    assert db.questions.find_one({"_id": ObjectId(old_item["id"])}) == original
    new_survey = client.post("/api/v1/surveys", headers=owner, json={"title": "新问卷"}).json()
    selected = client.post(f"/api/v1/surveys/{new_survey['id']}/questions/from-library", headers=owner, json={
        "libraryQuestionId": imported.json()["id"], "versionId": imported.json()["currentVersionId"],
    })
    assert selected.status_code == 201 and selected.json()["id"] != old_item["id"]


def test_reusable_question_uses_first_stage_validation_and_keeps_version_content_separate(client, db):
    owner = register_and_login(client, "library_owner")
    url = "/api/v1/library/questions"
    invalid = client.post(url, headers=with_key(owner, "invalid-create-001"), json={
        "type": "multiple", "title": "无效数量", "options": ["甲", "乙"],
        "validation": {"maxSelections": 3},
    })
    assert invalid.status_code == 422
    assert db.libraryQuestions.count_documents({}) == 0

    created = make_question(client, owner)
    first = created["currentVersion"]
    assert created["currentVersionId"] == first["id"]
    assert first["versionNo"] == 1 and first["parentVersionId"] is None
    assert len({item["id"] for item in first["options"]}) == 2
    saved = db.questionVersions.find_one({"_id": ObjectId(first["id"])})
    assert not {"surveyId", "order", "jumpRules"} & saved.keys()
    assert {"type", "title", "required", "options", "validation"}.issubset(saved)

    repeat = client.post(url, headers=with_key(owner, "library-create-001"), json={
        "type": "single", "title": "常用题", "required": True, "options": ["甲", "乙"],
    })
    assert repeat.status_code == 200 and repeat.json() == created
    assert client.post(url, headers=with_key(owner, "library-create-001"), json={
        "type": "text", "title": "不同题目",
    }).status_code == 409
    assert db.libraryQuestions.count_documents({}) == db.questionVersions.count_documents({}) == 1


def test_new_versions_are_immutable_and_restoring_old_content_creates_another_version(client, db):
    owner = register_and_login(client, "version_owner")
    question = make_question(client, owner)
    first = question["currentVersion"]
    first_saved = db.questionVersions.find_one({"_id": ObjectId(first["id"])})
    url = f"/api/v1/library/questions/{question['id']}/versions"
    second_result = client.post(url, headers=with_key(owner, "version-create-002"), json=version_payload(first))
    assert second_result.status_code == 201, second_result.text
    second = second_result.json()
    assert second["versionNo"] == 2 and second["parentVersionId"] == first["id"]
    assert second["options"][0]["id"] == first["options"][0]["id"]
    assert second["options"][1]["id"] not in {option["id"] for option in first["options"]}
    assert db.questionVersions.find_one({"_id": ObjectId(first["id"])}) == first_saved
    repeated_edit = client.post(url, headers=with_key(owner, "version-create-002"), json=version_payload(first))
    assert repeated_edit.status_code == 200 and repeated_edit.json()["id"] == second["id"]
    assert client.post(url, headers=with_key(owner, "version-create-002"), json=version_payload(first, title="不同请求内容")).status_code == 409
    assert client.put(f"{url}/{first['id']}", headers=owner, json={"title": "覆盖"}).status_code in {404, 405}
    assert db.questionVersions.find_one({"_id": ObjectId(first["id"])}) == first_saved
    assert client.post(url, headers=with_key(owner, "version-bad-option"), json={
        **version_payload(first), "options": [{"id": "not-from-parent", "label": "甲"}, {"label": "乙"}],
    }).status_code == 422

    restored_result = client.post(f"{url}/{first['id']}/restore", headers=with_key(owner, "version-restore-003"))
    assert restored_result.status_code == 201, restored_result.text
    restored = restored_result.json()
    assert restored["versionNo"] == 3 and restored["parentVersionId"] == first["id"]
    for field in ("type", "title", "required", "options", "validation"):
        assert restored[field] == first[field]
    assert [v["id"] for v in client.get(url, headers=owner).json()] == [first["id"], second["id"], restored["id"]]
    assert client.get(f"/api/v1/library/questions/{question['id']}", headers=owner).json()["currentVersionId"] == restored["id"]
    repeat = client.post(f"{url}/{first['id']}/restore", headers=with_key(owner, "version-restore-003"))
    assert repeat.status_code == 200 and repeat.json()["id"] == restored["id"]
    assert db.questionVersions.count_documents({}) == 3


def test_bank_items_pin_versions_and_require_explicit_switch(client, db):
    owner = register_and_login(client, "bank_item_owner")
    bank = make_bank(client, owner)
    question = make_question(client, owner)
    first = question["currentVersion"]
    base = f"/api/v1/question-banks/{bank['id']}/items"
    body = {"libraryQuestionId": question["id"], "selectedVersionId": first["id"]}
    added = client.post(base, headers=owner, json=body)
    assert added.status_code == 201, added.text
    assert added.json()["selectedVersionId"] == first["id"]
    version_url = f"/api/v1/library/questions/{question['id']}/versions"
    second = client.post(version_url, headers=with_key(owner, "bank-version-002"), json=version_payload(first)).json()
    assert client.get(base, headers=owner).json()[0]["selectedVersionId"] == first["id"]
    assert client.post(base, headers=owner, json=body).status_code == 200
    assert client.post(base, headers=owner, json={**body, "selectedVersionId": second["id"]}).status_code == 409
    assert client.get(base, headers=owner).json()[0]["selectedVersionId"] == first["id"]

    switch_url = f"{base}/{question['id']}/version"
    switched = client.put(switch_url, headers=owner, json={
        "expectedVersionId": first["id"], "selectedVersionId": second["id"],
    })
    assert switched.status_code == 200 and switched.json()["selectedVersionId"] == second["id"]
    assert client.put(switch_url, headers=owner, json={
        "expectedVersionId": first["id"], "selectedVersionId": second["id"],
    }).status_code == 200
    assert client.put(switch_url, headers=owner, json={
        "expectedVersionId": first["id"], "selectedVersionId": first["id"],
    }).status_code == 409
    unrelated = make_question(client, owner, key="unrelated-question", title="另一个逻辑题目")
    assert client.put(switch_url, headers=owner, json={
        "expectedVersionId": second["id"], "selectedVersionId": unrelated["currentVersionId"],
    }).status_code == 404
    assert client.delete(f"{base}/{question['id']}", headers=owner).status_code == 204
    assert client.delete(f"{base}/{question['id']}", headers=owner).status_code == 204
    assert client.get(base, headers=owner).json() == []
    assert db.questionBankItems.count_documents({}) == 0


def test_other_users_cannot_read_or_modify_banks_questions_or_versions(client):
    owner = register_and_login(client, "private_owner")
    other = register_and_login(client, "private_other")
    bank = make_bank(client, owner)
    question = make_question(client, owner)
    first = question["currentVersion"]
    other_bank = make_bank(client, other, key="other-bank-create")
    question_url = f"/api/v1/library/questions/{question['id']}"
    assert client.get(question_url, headers=other).status_code == 404
    assert client.get(f"{question_url}/versions", headers=other).status_code == 404
    assert client.post(f"{question_url}/versions", headers=with_key(other, "other-edit-001"), json=version_payload(first)).status_code == 404
    assert client.post(f"{question_url}/versions/{first['id']}/restore", headers=with_key(other, "other-restore-001")).status_code == 404
    assert client.post(f"/api/v1/question-banks/{other_bank['id']}/items", headers=other, json={
        "libraryQuestionId": question["id"], "selectedVersionId": first["id"],
    }).status_code == 404
    assert client.get(f"/api/v1/question-banks/{bank['id']}/items", headers=other).status_code == 404
    assert client.get("/api/v1/library/questions", headers=other).json() == []


def test_interrupted_first_version_can_be_completed_by_same_request(client, db, monkeypatch):
    owner = register_and_login(client, "first_retry_owner")
    original = db.questionVersions.insert_one
    failed = False

    def fail_once(document):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("simulated write interruption")
        return original(document)

    monkeypatch.setattr(db.questionVersions, "insert_one", fail_once)
    url = "/api/v1/library/questions"
    body = {"type": "text", "title": "可恢复题目"}
    with pytest.raises(RuntimeError, match="simulated write interruption"):
        client.post(url, headers=with_key(owner, "first-retry-key"), json=body)
    assert db.libraryQuestions.count_documents({}) == 1
    assert db.questionVersions.count_documents({}) == 0
    assert client.get(url, headers=owner).json() == []
    retry = client.post(url, headers=with_key(owner, "first-retry-key"), json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["currentVersion"]["versionNo"] == 1
    assert db.libraryQuestions.count_documents({}) == db.questionVersions.count_documents({}) == 1


def test_first_version_inserted_but_pointer_not_updated_can_be_retried(client, db, monkeypatch):
    owner = register_and_login(client, "first_pointer_retry_owner")
    original = library_service._finalize_pending
    failed = False

    def fail_once(database, logical, version):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("simulated first pointer interruption")
        return original(database, logical, version)

    monkeypatch.setattr(library_service, "_finalize_pending", fail_once)
    url = "/api/v1/library/questions"
    body = {"type": "text", "title": "首版本指针恢复"}
    with pytest.raises(RuntimeError, match="simulated first pointer interruption"):
        client.post(url, headers=with_key(owner, "first-pointer-key"), json=body)
    assert db.libraryQuestions.count_documents({}) == db.questionVersions.count_documents({}) == 1
    assert db.libraryQuestions.find_one({})["currentVersionId"] is None
    retry = client.post(url, headers=with_key(owner, "first-pointer-key"), json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["currentVersionId"] is not None
    assert db.questionVersions.count_documents({}) == 1


def test_interrupted_pointer_update_can_be_completed_by_same_request(client, db, monkeypatch):
    owner = register_and_login(client, "pointer_retry_owner")
    question = make_question(client, owner)
    first = question["currentVersion"]
    original = library_service._finalize_pending
    failed = False

    def fail_once(database, logical, version):
        nonlocal failed
        if not failed and version["versionNo"] == 2:
            failed = True
            raise RuntimeError("simulated finalize interruption")
        return original(database, logical, version)

    monkeypatch.setattr(library_service, "_finalize_pending", fail_once)
    url = f"/api/v1/library/questions/{question['id']}/versions"
    body = version_payload(first)
    with pytest.raises(RuntimeError, match="simulated finalize interruption"):
        client.post(url, headers=with_key(owner, "finalize-retry-key"), json=body)
    assert db.questionVersions.count_documents({}) == 2
    assert db.libraryQuestions.find_one({"_id": ObjectId(question["id"])})["currentVersionId"] == ObjectId(first["id"])
    retry = client.post(url, headers=with_key(owner, "finalize-retry-key"), json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["versionNo"] == 2
    assert db.libraryQuestions.find_one({"_id": ObjectId(question["id"])})["currentVersionId"] == ObjectId(retry.json()["id"])


def test_competing_version_writes_do_not_both_change_current_pointer(client, db, monkeypatch):
    owner = register_and_login(client, "concurrent_version_owner")
    question = make_question(client, owner)
    first = question["currentVersion"]
    saved = library_service.owned_library_question(db, question["id"], ObjectId(question["ownerId"]))
    payload = LibraryVersionInput.model_validate(version_payload(first))
    reserved = Event()
    release = Event()
    original = library_service._finish_pending

    def pause_after_reservation(*args, **kwargs):
        if args[3] == "concurrent-key-one":
            reserved.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(library_service, "_finish_pending", pause_after_reservation)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first_future = workers.submit(library_service.create_version, db, saved, ObjectId(question["ownerId"]), payload, "concurrent-key-one")
        assert reserved.wait(5)
        with pytest.raises(HTTPException) as error:
            library_service.create_version(db, saved, ObjectId(question["ownerId"]), payload, "concurrent-key-two")
        assert error.value.status_code == 409
        release.set()
        created, replayed = first_future.result(timeout=5)
    assert not replayed and created["versionNo"] == 2
    assert db.questionVersions.count_documents({}) == 2
