from datetime import datetime, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.db import get_db
from app.models import JumpRulesInput, QuestionInput, SurveyInput, SurveyUpdate
from app.security import current_user
from app.services.jumps import validate_jump_rules
from app.services.surveys import configuration_revision_filter, owned_survey, question_view, survey_view
from app.services.sharing import validate_source_reference


router = APIRouter(prefix="/api/v1/surveys", tags=["surveys"])
public_router = APIRouter(prefix="/api/v1/public/surveys", tags=["public surveys"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_survey(payload: SurveyInput, user: dict = Depends(current_user), db: Database = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    document = {
        "ownerId": user["_id"],
        "title": payload.title,
        "description": payload.description,
        "allowAnonymous": payload.allow_anonymous,
        "allowMultipleSubmissions": payload.allow_multiple_submissions,
        "status": "draft",
        "activeQuestionMutations": 0,
        "activeSubmissions": 0,
        "configurationRevision": 0,
        "submissionRevision": 0,
        "deadlineAt": payload.deadline_at,
        "createdAt": now,
        "updatedAt": now,
        "publishedAt": None,
        "closedAt": None,
        "schemaVersion": 1,
    }
    for _ in range(3):
        document["slug"] = token_urlsafe(9)
        try:
            document["_id"] = db.surveys.insert_one(document).inserted_id
            return survey_view(document)
        except DuplicateKeyError:
            document.pop("_id", None)
    raise HTTPException(status_code=500, detail="无法生成问卷链接")


@router.get("")
def list_surveys(user: dict = Depends(current_user), db: Database = Depends(get_db)) -> list[dict]:
    items = db.surveys.find({"ownerId": user["_id"]}).sort("createdAt", -1)
    return [survey_view(item) for item in items]


@router.get("/{survey_id}")
def get_survey(survey_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)) -> dict:
    return survey_view(owned_survey(db, survey_id, user["_id"]))


@router.patch("/{survey_id}")
def update_survey(survey_id: str, payload: SurveyUpdate, user: dict = Depends(current_user), db: Database = Depends(get_db)) -> dict:
    survey = owned_survey(db, survey_id, user["_id"])
    changes = payload.model_dump(by_alias=True, exclude_unset=True)
    if not changes:
        return survey_view(survey)
    if "title" in changes and changes["title"] is None:
        raise HTTPException(status_code=422, detail="标题不能为空")
    if "description" in changes and changes["description"] is None:
        raise HTTPException(status_code=422, detail="说明不能为空")
    locked_settings = {"allowAnonymous", "allowMultipleSubmissions"} & changes.keys()
    if any(changes[key] is None for key in locked_settings):
        raise HTTPException(status_code=422, detail="匿名与重复填写设置不能为空")
    if survey["status"] != "draft" and locked_settings:
        raise HTTPException(status_code=409, detail="发布后不能修改匿名或重复填写设置")
    if changes.get("deadlineAt") is not None:
        value = changes["deadlineAt"]
        if value.tzinfo is None or value <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="截止时间必须是带时区的未来时间")
        changes["deadlineAt"] = value.astimezone(timezone.utc)
    changes["updatedAt"] = datetime.now(timezone.utc)
    criteria = {
        "_id": survey["_id"], "status": survey["status"],
        "activeQuestionMutations": {"$in": [0, None]},
        **configuration_revision_filter(survey),
    }
    result = db.surveys.update_one(criteria, {"$set": changes, "$inc": {"configurationRevision": 1}})
    if result.matched_count != 1:
        raise HTTPException(status_code=409, detail="问卷配置或状态已变化，或题目正在保存，请刷新后重试")
    survey.update(changes)
    return survey_view(survey)


@router.post("/{survey_id}/publish")
def publish_survey(survey_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)) -> dict:
    survey = owned_survey(db, survey_id, user["_id"])
    if survey["status"] != "draft":
        raise HTTPException(status_code=409, detail="只有草稿问卷可以发布")
    deadline = survey.get("deadlineAt")
    if deadline is not None and (deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="截止时间已过，请先修改")
    questions = list(db.questions.find({"surveyId": survey["_id"]}).sort("order", 1))
    if not questions:
        raise HTTPException(status_code=409, detail="至少添加一道题目才能发布")
    for question in questions:
        try:
            validate_source_reference(db, question)
            option_ids = [option["id"] for option in question["options"]]
            if any(not isinstance(option_id, str) or not option_id or len(option_id) > 100 for option_id in option_ids) or len(option_ids) != len(set(option_ids)):
                raise ValueError("选项标识无效或重复")
            QuestionInput.model_validate({
                "type": question["type"], "title": question["title"], "required": question["required"],
                "options": [option["label"] for option in question["options"]], "validation": question["validation"],
            }, strict=True)
            if any(not isinstance(rule, dict) or not rule.get("id") for rule in question["jumpRules"]):
                raise ValueError("已保存规则缺少标识")
            saved_rules = JumpRulesInput.model_validate({"rules": question["jumpRules"]}, strict=True).rules
            validate_jump_rules(question, questions, saved_rules)
        except (ValidationError, HTTPException, KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=409, detail=f"第 {question['order']} 题的题目设置或跳转规则无效，请检查") from error
    now = datetime.now(timezone.utc)
    changes = {"status": "published", "publishedAt": now, "updatedAt": now}
    result = db.surveys.update_one({
        "_id": survey["_id"], "status": "draft",
        "activeQuestionMutations": {"$in": [0, None]},
        **configuration_revision_filter(survey),
        "$or": [{"deadlineAt": None}, {"deadlineAt": {"$gt": now}}],
    }, {"$set": changes})
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="发布检查期间问卷配置或状态已变化、截止时间已过或题目正在保存，请刷新后重试")
    survey.update(changes)
    return survey_view(survey)


@router.post("/{survey_id}/close")
def close_survey(survey_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)) -> dict:
    survey = owned_survey(db, survey_id, user["_id"])
    if survey["status"] != "published":
        raise HTTPException(status_code=409, detail="只有已发布的问卷可以关闭")
    now = datetime.now(timezone.utc)
    changes = {"status": "closed", "closedAt": now, "updatedAt": now}
    result = db.surveys.update_one({
        "_id": survey["_id"], "status": "published",
        "activeSubmissions": {"$in": [0, None]},
    }, {"$set": changes})
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="仍有答卷正在提交，请稍后重试关闭")
    survey.update(changes)
    return survey_view(survey)


@public_router.get("/{slug}")
def public_survey(slug: str, user: dict = Depends(current_user), db: Database = Depends(get_db)) -> dict:
    survey = db.surveys.find_one({"slug": slug, "status": {"$in": ["published", "closed"]}})
    if survey is None:
        raise HTTPException(status_code=404, detail="问卷未发布或不存在")
    view = survey_view(survey)
    public_fields = ("slug", "title", "description", "allowAnonymous", "allowMultipleSubmissions", "availability", "deadlineAt")
    questions = db.questions.find({"surveyId": survey["_id"]}).sort("order", 1)
    public_view = {key: view[key] for key in public_fields}
    public_view["hasSubmitted"] = db.responses.find_one({
        "surveyId": survey["_id"], "respondentId": user["_id"],
    }) is not None
    return {"survey": public_view, "questions": [question_view(item) for item in questions]}
