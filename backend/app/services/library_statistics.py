"""Aggregate totals for committed reusable-question versions."""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import json
from math import fsum, isfinite

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.services.library import committed_version, owned_library_question
from app.services.sharing import CONTENT_FIELDS, validate_source_reference
from app.services.surveys import owned_survey, parse_object_id


MIN_CONTRIBUTORS = 5
TARGET_NUMBER_BINS = 5
CHANGED = "统计期间提交或题目范围已变化，请刷新后重试"


def _valid_instances(
    db: Database, logical_id: ObjectId, version_id: ObjectId | None = None,
    version_ids: list[ObjectId] | None = None,
) -> list[dict]:
    criteria = {"sourceLibraryQuestionId": logical_id, "sourceVersionId": {"$exists": True}}
    if version_id is not None:
        criteria["sourceVersionId"] = version_id
    if version_ids is not None:
        criteria["sourceVersionId"] = {"$in": version_ids}
    instances = []
    for question in db.questions.find(criteria):
        try:
            validate_source_reference(db, question)
        except ValueError:
            continue
        instances.append(question)
    return instances


def consent_view(consent: dict | None) -> dict:
    return {"granted": consent is not None and consent.get("revokedAt") is None}


def set_consent(db: Database, survey_id: str, question_id: str, owner_id: ObjectId, *, grant: bool) -> dict:
    survey = owned_survey(db, survey_id, owner_id)
    logical_id = parse_object_id(question_id)
    logical = db.libraryQuestions.find_one({"_id": logical_id})
    if logical is None or not logical.get("currentVersionId"):
        raise HTTPException(status_code=404, detail="题库题目不存在")
    key = {"surveyId": survey["_id"], "libraryQuestionId": logical_id}
    # The owner can authorize an existing snapshot even if the sharing grant was revoked.
    if grant and not any(item["surveyId"] == survey["_id"] for item in _valid_instances(db, logical_id)):
        raise HTTPException(status_code=409, detail="问卷没有该题目的有效来源快照")
    existing = db.crossSurveyConsents.find_one(key)
    if existing is None:
        if not grant:
            return {"granted": False}
        now = datetime.now(timezone.utc)
        try:
            db.crossSurveyConsents.insert_one({
                **key, "grantedById": owner_id, "revision": 1,
                "createdAt": now, "updatedAt": now, "schemaVersion": 2,
            })
            return {"granted": True}
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="授权状态已变化，请重试") from None
    if (existing.get("revokedAt") is None) == grant:
        return {"granted": grant}
    update = {"$inc": {"revision": 1}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
    if grant:
        update["$unset"] = {"revokedAt": ""}
    else:
        update["$set"]["revokedAt"] = datetime.now(timezone.utc)
    changed = db.crossSurveyConsents.update_one({
        **key, "_id": existing["_id"], "revision": existing["revision"],
        "revokedAt": existing.get("revokedAt"),
    }, update)
    if changed.modified_count != 1:
        raise HTTPException(status_code=409, detail="授权状态已变化，请重试")
    return {"granted": grant}


def get_consent(db: Database, survey_id: str, question_id: str, owner_id: ObjectId) -> dict:
    survey = owned_survey(db, survey_id, owner_id)
    logical_id = parse_object_id(question_id)
    return consent_view(db.crossSurveyConsents.find_one({
        "surveyId": survey["_id"], "libraryQuestionId": logical_id,
    }))


def _scope(db: Database, logical: dict, versions: list[dict], *, include_all: bool = False) -> tuple[dict, tuple]:
    instances = _valid_instances(db, logical["_id"], version_ids=[version["_id"] for version in versions])
    by_survey = defaultdict(set)
    for instance in instances:
        by_survey[instance["surveyId"]].add(str(instance["_id"]))
    surveys = {}
    signature = []
    for survey_id in sorted(by_survey, key=str):
        survey = db.surveys.find_one({"_id": survey_id})
        if survey is None:
            continue
        consent = None if include_all else db.crossSurveyConsents.find_one({
            "surveyId": survey_id, "libraryQuestionId": logical["_id"],
        })
        consent_state = None if consent is None else (consent["revision"], consent.get("revokedAt"))
        eligible = include_all or survey["ownerId"] == logical["ownerId"] or (
            consent is not None and consent.get("revokedAt") is None
        )
        signature.append((survey_id, survey["ownerId"], tuple(sorted(by_survey[survey_id])), consent_state))
        if eligible:
            surveys[survey_id] = (survey, by_survey[survey_id])
    return surveys, tuple(signature)


def _submission_state(db: Database, survey_ids: list[ObjectId]) -> dict:
    states = {}
    for survey_id in survey_ids:
        survey = db.surveys.find_one({"_id": survey_id}, {"activeSubmissions": 1, "submissionRevision": 1})
        if survey is None or survey.get("activeSubmissions", 0):
            raise HTTPException(status_code=409, detail=CHANGED)
        states[survey_id] = survey.get("submissionRevision", 0)
    return states


def _numeric_distribution(values: list[tuple[float, ObjectId]]) -> tuple[list[dict], bool]:
    """Group one numeric value per response into readable equal-width bins.

    Boundaries are rounded to a 1/2/5 power-of-ten step and can change as new
    responses arrive. Bin counts retain one
    response per value; contributor sets enforce the same disclosure threshold
    as option counts.
    """
    if not values:
        return [], False
    numbers = [Decimal(str(value)) for value, _ in values]
    smallest, largest = min(numbers), max(numbers)
    if smallest == largest:
        people = {respondent for _, respondent in values}
        return [{"lowerBound": float(smallest), "upperBound": float(largest),
                 "upperInclusive": True, "count": len(values)}], 0 < len(people) < MIN_CONTRIBUTORS

    raw_step = (largest - smallest) / TARGET_NUMBER_BINS
    unit = Decimal(10) ** raw_step.adjusted()
    step = next(unit * factor for factor in (1, 2, 5, 10) if raw_step <= unit * factor)
    lower = (smallest / step).to_integral_value(rounding=ROUND_FLOOR) * step
    upper = (largest / step).to_integral_value(rounding=ROUND_CEILING) * step
    count = max(1, int((upper - lower) / step))
    bins = [{"lowerBound": float(lower + step * index),
             "upperBound": float(lower + step * (index + 1)),
             "upperInclusive": index == count - 1, "count": 0}
            for index in range(count)]
    people_by_bin = [set() for _ in bins]
    for value, respondent in values:
        index = int((Decimal(str(value)) - lower) // step)
        index = min(max(index, 0), count - 1)
        bins[index]["count"] += 1
        people_by_bin[index].add(respondent)
    small_bin = any(0 < len(people) < MIN_CONTRIBUTORS for people in people_by_bin)
    return bins, small_bin


def _aggregate_statistics(db: Database, logical: dict, versions: list[dict], *, include_all: bool) -> dict:
    version = versions[0]
    scope, signature = _scope(db, logical, versions, include_all=include_all)
    survey_ids = list(scope)
    revisions = _submission_state(db, survey_ids)
    option_ids = [option["id"] for option in version["options"]]
    option_counts = {option_id: 0 for option_id in option_ids}
    option_contributors = {option_id: set() for option_id in option_ids}
    contributors = {"response": set(), "reached": set(), "answered": set()}
    response_count = reached_count = answered_count = 0
    numbers = []
    numeric_contributions = []
    text_counts = defaultdict(int)
    text_contributors = defaultdict(set)
    if survey_ids:
        cursor = db.responses.find({"surveyId": {"$in": survey_ids}}, {
            "surveyId": 1, "respondentId": 1, "visitedQuestionIds": 1, "answers": 1,
        }).batch_size(100)
        for response in cursor:
            relevant = scope.get(response["surveyId"])
            if relevant is None:
                continue
            ids = relevant[1]
            respondent = response["respondentId"]
            response_count += 1
            contributors["response"].add(respondent)
            visited = set(response.get("visitedQuestionIds", []))
            if ids.intersection(visited):
                reached_count += 1
                contributors["reached"].add(respondent)
            # Answer documents for a skipped question are ignored. Each response
            # contributes at most once even when the version appears twice.
            values_by_question = {}
            for answer in response.get("answers", []):
                answer_id = answer.get("questionId")
                if answer_id in ids and answer_id in visited and answer_id not in values_by_question:
                    values_by_question[answer_id] = answer["value"]
            answers = list(values_by_question.values())
            if not answers:
                continue
            answered_count += 1
            contributors["answered"].add(respondent)
            if version["type"] in ("single", "multiple"):
                chosen = set()
                for value in answers:
                    if version["type"] == "single" and isinstance(value, str):
                        chosen.add(value)
                    elif version["type"] == "multiple" and isinstance(value, list):
                        chosen.update(item for item in value if isinstance(item, str))
                for option_id in chosen.intersection(option_counts):
                    option_counts[option_id] += 1
                    option_contributors[option_id].add(respondent)
            elif version["type"] == "number":
                values = [float(value) for value in answers
                          if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)]
                if values:
                    mean = fsum(values) / len(values)
                    numbers.append(mean)
                    numeric_contributions.append((mean, respondent))
            elif version["type"] == "text":
                for value in {item.strip() for item in answers if isinstance(item, str) and item.strip()}:
                    text_counts[value] += 1
                    text_contributors[value].add(respondent)
    # Conservative small-sample rule: suppress all respondent-level fields if
    # any nonzero released count or average has fewer than five distinct people.
    small_count = any(0 < count < MIN_CONTRIBUTORS for count in map(len, contributors.values()))
    small_option = any(0 < len(people) < MIN_CONTRIBUTORS for people in option_contributors.values())
    numeric_distribution, small_numeric_bin = _numeric_distribution(numeric_contributions) if version["type"] == "number" else ([], False)
    suppressed = small_count or small_option or small_numeric_bin
    if _scope(db, logical, versions, include_all=include_all)[1] != signature or _submission_state(db, survey_ids) != revisions:
        raise HTTPException(status_code=409, detail=CHANGED)
    result = {
        "scope": "all_surveys" if include_all else "owned_surveys_and_explicit_consent",
        "participatingSurveyCount": len(scope),
        "suppression": {"applied": suppressed, "minimumDistinctRespondents": MIN_CONTRIBUTORS},
        "responseCount": None if suppressed else response_count,
        "reachedCount": None if suppressed else reached_count,
        "answeredCount": None if suppressed else answered_count,
    }
    if version["type"] in ("single", "multiple"):
        result["optionCounts"] = None if suppressed else [
            {"optionId": option_id, "count": option_counts[option_id]} for option_id in option_ids
        ]
    elif version["type"] == "number":
        result["average"] = None if suppressed or not numbers else fsum(numbers) / len(numbers)
        result["numericDistribution"] = None if suppressed else numeric_distribution
    elif version["type"] == "text":
        result["textAnswerCounts"] = None if suppressed else [
            {"value": value, "count": count}
            for value, count in sorted(text_counts.items(), key=lambda item: (-item[1], item[0]))
            if len(text_contributors[value]) >= MIN_CONTRIBUTORS
        ]
    return result


def version_statistics(db: Database, question_id: str, version_id: str, owner_id: ObjectId) -> dict:
    """Existing consent-scoped route remains available for older clients."""
    logical = owned_library_question(db, question_id, owner_id)
    version = committed_version(db, logical, version_id)
    return _aggregate_statistics(db, logical, [version], include_all=False)


def all_version_statistics(db: Database, question_id: str, version_id: str, owner_id: ObjectId) -> dict:
    logical = owned_library_question(db, question_id, owner_id)
    version = committed_version(db, logical, version_id)
    return _aggregate_statistics(db, logical, [version], include_all=True)


def question_overview_statistics(db: Database, question_id: str, owner_id: ObjectId) -> dict:
    """Group only versions whose full answer semantics and option IDs match."""
    logical = owned_library_question(db, question_id, owner_id)
    versions = list(db.questionVersions.find({
        "libraryQuestionId": logical["_id"],
        "versionNo": {"$lte": logical.get("versionCounter", 0)},
    }).sort("versionNo", 1))
    groups = {}
    for version in versions:
        key = json.dumps({name: version[name] for name in CONTENT_FIELDS}, sort_keys=True, ensure_ascii=False)
        groups.setdefault(key, []).append(version)
    return {"groups": [
        {
            "versionIds": [str(version["_id"]) for version in group],
            "versionNumbers": [version["versionNo"] for version in group],
            "statistics": _aggregate_statistics(db, logical, group, include_all=True),
        }
        for group in groups.values()
    ]}
