"""Minimal owner-only additions needed by the library UI."""

from bson import ObjectId

from conftest import register_and_login


def test_browser_preflight_allows_idempotency_key(client):
    preflight = client.options("/api/v1/library/questions", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
    })
    assert preflight.status_code == 200
    assert "idempotency-key" in preflight.headers["access-control-allow-headers"].lower()


def test_share_by_username_keeps_owner_check_and_id_contract(client, db):
    owner = register_and_login(client, "display_owner")
    recipient = register_and_login(client, "display_recipient")
    outsider = register_and_login(client, "display_outsider")
    question = client.post("/api/v1/library/questions", headers={**owner, "Idempotency-Key": "display-question-001"},
                           json={"type": "text", "title": "可分享"}).json()
    path = f"/api/v1/library/questions/{question['id']}/shares"
    assert client.post(path, headers=outsider, json={"recipientUsername": "display_recipient"}).status_code == 404
    assert client.post(path, headers=owner, json={"recipientUsername": "unknown_user"}).status_code == 404
    assert client.post(path, headers=owner, json={"recipientUsername": "display_owner"}).status_code == 422
    assert client.post(path, headers=owner, json={"recipientUsername": "display_recipient", "recipientUserId": str(ObjectId())}).status_code == 422
    granted = client.post(path, headers=owner, json={"recipientUsername": "DISPLAY_RECIPIENT"})
    assert granted.status_code == 201, granted.text
    assert granted.json()["recipientUserId"] == str(db.users.find_one({"usernameKey": "display_recipient"})["_id"])
    assert granted.json()["recipientUsername"] == "display_recipient"
    assert client.get(path, headers=owner).json()[0]["recipientUsername"] == "display_recipient"
    assert client.post(path, headers=owner, json={"recipientUserId": granted.json()["recipientUserId"]}).status_code == 200
    assert client.get("/api/v1/library/shared/questions", headers=recipient).json()[0]["id"] == question["id"]


def test_owner_sees_source_ids_but_public_filling_does_not(client, db):
    owner = register_and_login(client, "metadata_owner")
    logical = client.post("/api/v1/library/questions", headers={**owner, "Idempotency-Key": "metadata-question-001"},
                          json={"type": "text", "title": "来源题"}).json()
    survey = client.post("/api/v1/surveys", headers=owner, json={"title": "来源问卷"}).json()
    base = f"/api/v1/surveys/{survey['id']}"
    selected = client.post(f"{base}/questions/from-library", headers=owner, json={
        "libraryQuestionId": logical["id"], "versionId": logical["currentVersionId"],
    })
    assert selected.status_code == 201
    assert selected.json()["sourceLibraryQuestionId"] == logical["id"]
    assert selected.json()["sourceVersionId"] == logical["currentVersionId"]
    assert client.get(f"{base}/questions", headers=owner).json()[0]["sourceVersionId"] == logical["currentVersionId"]
    assert client.post(f"{base}/publish", headers=owner).status_code == 200
    public = client.get(f"/api/v1/public/surveys/{survey['slug']}", headers=owner)
    assert public.status_code == 200, public.text
    assert "sourceLibraryQuestionId" not in public.text and "sourceVersionId" not in public.text


def test_owner_edit_response_drops_source_after_content_change(client):
    owner = register_and_login(client, "metadata_edit_owner")
    logical = client.post("/api/v1/library/questions", headers={**owner, "Idempotency-Key": "metadata-edit-question"},
                          json={"type": "text", "title": "原内容"}).json()
    survey = client.post("/api/v1/surveys", headers=owner, json={"title": "待编辑问卷"}).json()
    base = f"/api/v1/surveys/{survey['id']}"
    selected = client.post(f"{base}/questions/from-library", headers=owner, json={
        "libraryQuestionId": logical["id"], "versionId": logical["currentVersionId"],
    }).json()
    edited = client.put(f"{base}/questions/{selected['id']}", headers=owner,
                        json={"type": "text", "title": "改后内容", "options": [], "validation": {}})
    assert edited.status_code == 200
    assert "sourceLibraryQuestionId" not in edited.json() and "sourceVersionId" not in edited.json()
    assert "sourceVersionId" not in client.get(f"{base}/questions", headers=owner).json()[0]
