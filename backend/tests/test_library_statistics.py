from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.services import library_statistics as service
from conftest import register_and_login


@pytest.fixture(autouse=True)
def consent_index(db):
    db.crossSurveyConsents.create_index([("surveyId", 1), ("libraryQuestionId", 1)], unique=True)


def account(client, db, name):
    headers = register_and_login(client, name)
    return headers, db.users.find_one({"username": name})["_id"]


def library_question(client, owner, kind="single", key="statistics-question-001"):
    payload = {"type": kind, "title": "私有内容", "required": False}
    if kind in ("single", "multiple"):
        payload["options"] = ["甲", "乙"]
    response = client.post("/api/v1/library/questions", headers={**owner, "Idempotency-Key": key}, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def survey(client, owner, title="私有问卷"):
    response = client.post("/api/v1/surveys", headers=owner, json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def select(client, owner, survey_id, logical, version_id=None):
    response = client.post(f"/api/v1/surveys/{survey_id}/questions/from-library", headers=owner, json={
        "libraryQuestionId": logical["id"], "versionId": version_id or logical["currentVersionId"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def share(client, owner, logical, recipient_id):
    response = client.post(f"/api/v1/library/questions/{logical['id']}/shares", headers=owner,
                           json={"recipientUserId": str(recipient_id)})
    assert response.status_code == 201, response.text


def consent_url(survey_id, logical):
    return f"/api/v1/surveys/{survey_id}/cross-survey-statistics/{logical['id']}/consent"


def stats_url(logical, version_id=None):
    return f"/api/v1/library/questions/{logical['id']}/versions/{version_id or logical['currentVersionId']}/cross-survey-statistics"


def all_stats_url(logical, version_id=None):
    return f"/api/v1/library/questions/{logical['id']}/versions/{version_id or logical['currentVersionId']}/all-survey-statistics"


def response(db, survey_id, respondent_id, visited, answers, anonymous=True):
    db.responses.insert_one({
        "surveyId": ObjectId(survey_id), "respondentId": respondent_id, "isAnonymous": anonymous,
        "visitedQuestionIds": visited, "answers": answers, "submittedAt": datetime.now(timezone.utc),
        "singleSubmission": False, "schemaVersion": 1,
    })


def test_owner_consent_revocation_and_scope_are_private(client, db):
    owner, owner_id = account(client, db, "cross_owner")
    peer, peer_id = account(client, db, "cross_peer")
    stranger, _ = account(client, db, "cross_stranger")
    logical = library_question(client, owner)
    own = survey(client, owner)
    other = survey(client, peer, "不能泄露的问卷名")
    own_item = select(client, owner, own["id"], logical)
    share(client, owner, logical, peer_id)
    other_item = select(client, peer, other["id"], logical)
    option = logical["currentVersion"]["options"][0]["id"]
    for index in range(5):
        response(db, own["id"], ObjectId(), [own_item["id"]], [{"questionId": own_item["id"], "value": option}])
        response(db, other["id"], ObjectId(), [other_item["id"]], [{"questionId": other_item["id"], "value": option}])
    url = stats_url(logical)
    assert client.get(url).status_code == 401
    assert client.get(url, headers=peer).status_code == 404
    assert client.get(url, headers=stranger).status_code == 404
    assert client.put(consent_url(other["id"], logical), headers=owner).status_code == 404
    assert client.put(consent_url(other["id"], logical), headers=stranger).status_code == 404
    before = client.get(url, headers=owner).json()
    assert before["participatingSurveyCount"] == 1
    assert (before["responseCount"], before["reachedCount"], before["answeredCount"]) == (5, 5, 5)
    assert client.put(consent_url(other["id"], logical), headers=peer).json() == {"granted": True}
    assert client.put(consent_url(other["id"], logical), headers=peer).json() == {"granted": True}
    granted = client.get(url, headers=owner).json()
    assert granted["participatingSurveyCount"] == 2
    assert (granted["responseCount"], granted["reachedCount"], granted["answeredCount"]) == (10, 10, 10)
    assert granted["optionCounts"] == [{"optionId": option, "count": 10}, {
        "optionId": logical["currentVersion"]["options"][1]["id"], "count": 0,
    }]
    assert granted["scope"] == "owned_surveys_and_explicit_consent"
    assert granted["suppression"] == {"applied": False, "minimumDistinctRespondents": 5}
    assert all(private not in str(granted) for private in [
        "不能泄露的问卷名", str(peer_id), str(owner_id), "respondentId", "answers", "isAnonymous",
    ])
    assert client.delete(consent_url(other["id"], logical), headers=peer).json() == {"granted": False}
    assert client.get(consent_url(other["id"], logical), headers=peer).json() == {"granted": False}
    after = client.get(url, headers=owner).json()
    assert after["participatingSurveyCount"] == 1 and after["responseCount"] == 5
    assert db.responses.count_documents({"surveyId": ObjectId(other["id"])}) == 5
    assert db.questions.find_one({"_id": ObjectId(other_item["id"])}) is not None


def test_same_version_multiple_instances_dedupe_skips_blanks_and_version_isolation(client, db):
    owner, _ = account(client, db, "cross_dedupe")
    logical = library_question(client, owner)
    first = logical["currentVersionId"]
    draft = survey(client, owner)
    a = select(client, owner, draft["id"], logical)
    b = select(client, owner, draft["id"], logical)
    options = [item["id"] for item in logical["currentVersion"]["options"]]
    second = client.post(f"/api/v1/library/questions/{logical['id']}/versions",
                         headers={**owner, "Idempotency-Key": "statistics-version-002"}, json={
        "parentVersionId": first, "type": "single", "title": "第二版", "options": [
            {"id": options[0], "label": "丙"}, {"id": options[1], "label": "丁"},
        ],
    })
    assert second.status_code == 201, second.text
    c = select(client, owner, draft["id"], logical, second.json()["id"])
    for _ in range(5):
        respondent = ObjectId()
        response(db, draft["id"], respondent, [a["id"], b["id"], c["id"]], [
            {"questionId": a["id"], "value": options[0]},
            {"questionId": b["id"], "value": options[0]},
            {"questionId": c["id"], "value": second.json()["options"][0]["id"]},
        ])
    old = client.get(stats_url(logical, first), headers=owner).json()
    new = client.get(stats_url(logical, second.json()["id"]), headers=owner).json()
    assert (old["responseCount"], old["reachedCount"], old["answeredCount"]) == (5, 5, 5)
    assert old["optionCounts"][0]["count"] == 5
    assert new["optionCounts"][0]["count"] == 5
    # A skipped instance and a visited but empty instance are not answers.
    response(db, draft["id"], ObjectId(), [a["id"]], [])
    response(db, draft["id"], ObjectId(), [c["id"]], [])
    updated = client.get(stats_url(logical, first), headers=owner).json()
    assert (updated["responseCount"], updated["reachedCount"], updated["answeredCount"]) == (7, 6, 5)
    assert updated["optionCounts"][0]["count"] == 5
    assert client.get(stats_url(logical, str(ObjectId())), headers=owner).status_code == 404


def test_invalid_snapshot_and_detached_source_are_excluded(client, db):
    owner, _ = account(client, db, "cross_snapshot")
    logical = library_question(client, owner, kind="text")
    draft = survey(client, owner)
    valid = select(client, owner, draft["id"], logical)
    invalid = select(client, owner, draft["id"], logical)
    detached = select(client, owner, draft["id"], logical)
    db.questions.update_one({"_id": ObjectId(invalid["id"])}, {"$set": {"title": "改了快照"}})
    db.questions.update_one({"_id": ObjectId(detached["id"])},
                            {"$unset": {"sourceLibraryQuestionId": "", "sourceVersionId": ""}})
    for _ in range(5):
        response(db, draft["id"], ObjectId(), [valid["id"], invalid["id"], detached["id"]], [
            {"questionId": invalid["id"], "value": "不可泄露的文本"},
            {"questionId": detached["id"], "value": "不可泄露的文本"},
        ])
    result = client.get(stats_url(logical), headers=owner).json()
    assert result["participatingSurveyCount"] == 1
    assert (result["responseCount"], result["reachedCount"], result["answeredCount"]) == (5, 5, 0)
    assert "optionCounts" not in result and "average" not in result
    assert "不可泄露的文本" not in str(result)


def test_small_sample_uses_distinct_respondents_and_option_suppression(client, db):
    owner, _ = account(client, db, "cross_small")
    logical = library_question(client, owner)
    draft = survey(client, owner)
    item = select(client, owner, draft["id"], logical)
    option = logical["currentVersion"]["options"][0]["id"]
    person = ObjectId()
    for _ in range(6):
        response(db, draft["id"], person, [item["id"]], [{"questionId": item["id"], "value": option}])
    result = client.get(stats_url(logical), headers=owner).json()
    assert result["suppression"]["applied"] is True
    assert result["participatingSurveyCount"] == 1
    assert all(result[key] is None for key in ["responseCount", "reachedCount", "answeredCount", "optionCounts"])
    for _ in range(4):
        response(db, draft["id"], ObjectId(), [item["id"]], [])
    result = client.get(stats_url(logical), headers=owner).json()
    assert result["suppression"]["applied"] is True  # option still has one contributor


def test_number_averages_one_value_per_response_and_no_raw_values(client, db):
    owner, _ = account(client, db, "cross_number")
    logical = library_question(client, owner, kind="number")
    draft = survey(client, owner)
    a = select(client, owner, draft["id"], logical)
    b = select(client, owner, draft["id"], logical)
    for _ in range(5):
        response(db, draft["id"], ObjectId(), [a["id"], b["id"]], [
            {"questionId": a["id"], "value": 10}, {"questionId": b["id"], "value": 30},
        ])
    result = client.get(stats_url(logical), headers=owner).json()
    assert result["average"] == 20
    assert result["answeredCount"] == 5
    assert result["numericDistribution"] == [{
        "lowerBound": 20.0, "upperBound": 20.0, "upperInclusive": True, "count": 5,
    }]
    assert "entries" not in result and "respondent" not in str(result)


def test_number_distribution_combines_authorized_surveys_and_suppresses_sparse_bins(client, db):
    author, _ = account(client, db, "cross_age_author")
    peer, peer_id = account(client, db, "cross_age_peer")
    logical = library_question(client, author, kind="number", key="statistics-age-question")
    own_survey = survey(client, author)
    peer_survey = survey(client, peer)
    own_item = select(client, author, own_survey["id"], logical)
    share(client, author, logical, peer_id)
    peer_item = select(client, peer, peer_survey["id"], logical)

    for _ in range(5):
        response(db, own_survey["id"], ObjectId(), [own_item["id"]], [
            {"questionId": own_item["id"], "value": 22},
        ])
        response(db, peer_survey["id"], ObjectId(), [peer_item["id"]], [
            {"questionId": peer_item["id"], "value": 42},
        ])
    url = stats_url(logical)
    before = client.get(url, headers=author).json()
    assert before["numericDistribution"] == [{
        "lowerBound": 22.0, "upperBound": 22.0, "upperInclusive": True, "count": 5,
    }]
    automatic_before_consent = client.get(all_stats_url(logical), headers=author).json()
    assert automatic_before_consent["scope"] == "all_surveys"
    assert automatic_before_consent["participatingSurveyCount"] == 2
    assert automatic_before_consent["responseCount"] == 10
    assert automatic_before_consent["average"] == 32
    assert [(item["lowerBound"], item["upperBound"], item["count"])
            for item in automatic_before_consent["numericDistribution"] if item["count"]] == [
                (20.0, 25.0, 5), (40.0, 45.0, 5),
            ]
    assert client.put(consent_url(peer_survey["id"], logical), headers=peer).status_code == 200
    result = client.get(url, headers=author).json()
    assert result["participatingSurveyCount"] == 2
    assert result["average"] == 32
    assert sum(item["count"] for item in result["numericDistribution"]) == 10
    assert [(item["lowerBound"], item["upperBound"], item["count"])
            for item in result["numericDistribution"] if item["count"]] == [
                (20.0, 25.0, 5), (40.0, 45.0, 5),
            ]

    response(db, peer_survey["id"], ObjectId(), [peer_item["id"]], [
        {"questionId": peer_item["id"], "value": 70},
    ])
    suppressed = client.get(url, headers=author).json()
    assert suppressed["suppression"]["applied"] is True
    assert suppressed["numericDistribution"] is None
    assert suppressed["average"] is None
    assert suppressed["responseCount"] is None
    automatic_sparse = client.get(all_stats_url(logical), headers=author).json()
    assert automatic_sparse["participatingSurveyCount"] == 2
    assert automatic_sparse["suppression"]["applied"] is True
    assert automatic_sparse["numericDistribution"] is None
    assert automatic_sparse["average"] is None
    assert automatic_sparse["responseCount"] is None


def test_all_surveys_include_shared_users_without_consent_and_preserve_legacy_scope(client, db):
    author, _ = account(client, db, "all_scope_author")
    peer, peer_id = account(client, db, "all_scope_peer")
    logical = library_question(client, author, key="all-scope-question")
    own_survey, peer_survey = survey(client, author), survey(client, peer)
    own_item = select(client, author, own_survey["id"], logical)
    share(client, author, logical, peer_id)
    peer_item = select(client, peer, peer_survey["id"], logical)
    option = logical["currentVersion"]["options"][0]["id"]
    for _ in range(5):
        response(db, own_survey["id"], ObjectId(), [own_item["id"]], [
            {"questionId": own_item["id"], "value": option},
        ])
        response(db, peer_survey["id"], ObjectId(), [peer_item["id"]], [
            {"questionId": peer_item["id"], "value": option},
        ])
    assert client.get(all_stats_url(logical), headers=peer).status_code == 404
    result = client.get(all_stats_url(logical), headers=author).json()
    assert result["scope"] == "all_surveys"
    assert (result["participatingSurveyCount"], result["responseCount"], result["answeredCount"]) == (2, 10, 10)
    assert result["optionCounts"][0]["count"] == 10
    legacy = client.get(stats_url(logical), headers=author).json()
    assert (
        legacy["participatingSurveyCount"], legacy["responseCount"],
        legacy["reachedCount"], legacy["answeredCount"],
    ) == (1, 5, 5, 5)


def test_overview_merges_only_identical_versions_and_text_shows_only_repeated_values(client, db):
    author, _ = account(client, db, "all_versions_author")
    logical = library_question(client, author, kind="text", key="all-versions-question")
    first = logical["currentVersionId"]
    url = f"/api/v1/library/questions/{logical['id']}/versions"
    same = client.post(url, headers={**author, "Idempotency-Key": "same-version-content"}, json={
        "parentVersionId": first, "type": "text", "title": "私有内容", "required": False,
        "options": [], "validation": {},
    })
    assert same.status_code == 201
    changed = client.post(url, headers={**author, "Idempotency-Key": "changed-version-title"}, json={
        "parentVersionId": first, "type": "text", "title": "不同问题", "required": False,
        "options": [], "validation": {},
    })
    assert changed.status_code == 201
    a, b, c = [survey(client, author, f"版本{i}") for i in range(3)]
    ai = select(client, author, a["id"], logical, first)
    bi = select(client, author, b["id"], logical, same.json()["id"])
    ci = select(client, author, c["id"], logical, changed.json()["id"])
    for _ in range(5):
        response(db, a["id"], ObjectId(), [ai["id"]], [{"questionId": ai["id"], "value": "重复答案"}])
        response(db, b["id"], ObjectId(), [bi["id"]], [{"questionId": bi["id"], "value": "重复答案"}])
        response(db, c["id"], ObjectId(), [ci["id"]], [{"questionId": ci["id"], "value": "其他版本答案"}])
    response(db, b["id"], ObjectId(), [bi["id"]], [{"questionId": bi["id"], "value": "只出现一次的私人内容"}])
    overview = client.get(f"/api/v1/library/questions/{logical['id']}/all-survey-statistics", headers=author).json()
    assert len(overview["groups"]) == 2
    first_group, changed_group = overview["groups"]
    assert first_group["versionNumbers"] == [1, 2]
    assert first_group["statistics"]["responseCount"] == 11
    assert first_group["statistics"]["textAnswerCounts"] == [{"value": "重复答案", "count": 10}]
    assert "只出现一次的私人内容" not in str(overview)
    assert changed_group["versionNumbers"] == [3]
    assert changed_group["statistics"]["textAnswerCounts"] == [{"value": "其他版本答案", "count": 5}]
    individual = client.get(all_stats_url(logical, same.json()["id"]), headers=author).json()
    assert individual["responseCount"] == 6
    assert individual["textAnswerCounts"] == [{"value": "重复答案", "count": 5}]


def test_submission_and_consent_change_during_scan_return_409(client, db, monkeypatch):
    owner, owner_id = account(client, db, "cross_race")
    peer, peer_id = account(client, db, "cross_race_peer")
    logical = library_question(client, owner)
    other = survey(client, peer)
    share(client, owner, logical, peer_id)
    select(client, peer, other["id"], logical)
    assert client.put(consent_url(other["id"], logical), headers=peer).status_code == 200
    original_find = db.responses.find

    def changed_revision(*args, **kwargs):
        db.surveys.update_one({"_id": ObjectId(other["id"])}, {"$inc": {"submissionRevision": 1}})
        return original_find(*args, **kwargs)

    monkeypatch.setattr(db.responses, "find", changed_revision)
    with pytest.raises(HTTPException) as error:
        service.version_statistics(db, logical["id"], logical["currentVersionId"], owner_id)
    assert error.value.status_code == 409
    monkeypatch.setattr(db.responses, "find", original_find)
    db.surveys.update_one({"_id": ObjectId(other["id"])}, {"$set": {"activeSubmissions": 1}})
    assert client.get(stats_url(logical), headers=owner).status_code == 409
    db.surveys.update_one({"_id": ObjectId(other["id"])}, {"$set": {"activeSubmissions": 0}})

    def changed_consent(*args, **kwargs):
        db.crossSurveyConsents.update_one({"surveyId": ObjectId(other["id"])},
                                          {"$inc": {"revision": 1}, "$set": {"revokedAt": datetime.now(timezone.utc)}})
        return original_find(*args, **kwargs)

    monkeypatch.setattr(db.responses, "find", changed_consent)
    with pytest.raises(HTTPException) as error:
        service.version_statistics(db, logical["id"], logical["currentVersionId"], owner_id)
    assert error.value.status_code == 409


def test_snapshot_detachment_during_scan_returns_409(client, db, monkeypatch):
    owner, owner_id = account(client, db, "cross_detach_race")
    logical = library_question(client, owner, kind="text")
    draft = survey(client, owner)
    item = select(client, owner, draft["id"], logical)
    response(db, draft["id"], ObjectId(), [item["id"]], [{"questionId": item["id"], "value": "private"}])
    original_find = db.responses.find

    def detached(*args, **kwargs):
        db.questions.update_one({"_id": ObjectId(item["id"])},
                                {"$unset": {"sourceLibraryQuestionId": "", "sourceVersionId": ""}})
        return original_find(*args, **kwargs)

    monkeypatch.setattr(db.responses, "find", detached)
    with pytest.raises(HTTPException) as error:
        service.version_statistics(db, logical["id"], logical["currentVersionId"], owner_id)
    assert error.value.status_code == 409
