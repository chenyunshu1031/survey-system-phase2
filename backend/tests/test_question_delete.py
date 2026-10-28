from bson import ObjectId

from conftest import register_and_login


def draft(client, headers):
    return client.post('/api/v1/surveys', headers=headers, json={'title': '删除测试'}).json()


def add(client, headers, survey_id, title='数字题'):
    result = client.post(f'/api/v1/surveys/{survey_id}/questions', headers=headers, json={
        'type': 'number', 'title': title, 'required': False, 'validation': {},
    })
    assert result.status_code == 201, result.text
    return result.json()


def test_delete_draft_snapshot_preserves_library_and_other_instances(client, db):
    owner = register_and_login(client, 'delete_owner')
    survey = draft(client, owner)
    logical = client.post('/api/v1/library/questions', headers={**owner, 'Idempotency-Key': 'delete-snapshot-test'},
                          json={'type': 'number', 'title': '共享年龄', 'required': False}).json()
    base = f"/api/v1/surveys/{survey['id']}/questions"
    instance = client.post(base + '/from-library', headers=owner, json={
        'libraryQuestionId': logical['id'], 'versionId': logical['currentVersionId'],
    }).json()
    retained = add(client, owner, survey['id'], '保留题')
    assert client.delete(base + '/' + instance['id'], headers=owner).status_code == 204
    assert client.get(base, headers=owner).json() == [retained]
    assert db.libraryQuestions.find_one({'_id': ObjectId(logical['id'])}) is not None
    assert db.questionVersions.count_documents({'libraryQuestionId': ObjectId(logical['id'])}) == 1
    assert client.delete(base + '/' + instance['id'], headers=owner).status_code == 404
    added = add(client, owner, survey['id'], '后续新增')
    assert added['order'] > retained['order']
    assert client.post(f"/api/v1/surveys/{survey['id']}/publish", headers=owner).status_code == 200


def test_delete_rejects_other_owner_other_survey_and_published_question(client, db):
    owner = register_and_login(client, 'delete_author')
    stranger = register_and_login(client, 'delete_stranger')
    survey = draft(client, owner)
    question = add(client, owner, survey['id'])
    url = f"/api/v1/surveys/{survey['id']}/questions/{question['id']}"
    assert client.delete(url).status_code == 401
    assert client.delete(url, headers=stranger).status_code == 404
    other = draft(client, owner)
    assert client.delete(f"/api/v1/surveys/{other['id']}/questions/{question['id']}", headers=owner).status_code == 404
    assert client.post(f"/api/v1/surveys/{survey['id']}/publish", headers=owner).status_code == 200
    assert client.delete(url, headers=owner).status_code == 409
    assert db.questions.find_one({'_id': ObjectId(question['id'])}) is not None


def test_delete_jump_target_requires_rule_removal_and_respects_mutation_fence(client, db):
    owner = register_and_login(client, 'delete_jump_owner')
    survey = draft(client, owner)
    source = add(client, owner, survey['id'], '起点')
    target = add(client, owner, survey['id'], '终点')
    base = f"/api/v1/surveys/{survey['id']}/questions"
    assert client.put(base + f"/{source['id']}/jump-rules", headers=owner, json={'rules': [{
        'priority': 1, 'operator': 'gt', 'value': 10, 'targetQuestionId': target['id'],
    }]}).status_code == 200
    assert client.delete(base + '/' + target['id'], headers=owner).status_code == 409
    assert db.questions.count_documents({'surveyId': ObjectId(survey['id'])}) == 2
    assert client.put(base + f"/{source['id']}/jump-rules", headers=owner, json={'rules': []}).status_code == 200
    db.surveys.update_one({'_id': ObjectId(survey['id'])}, {'$set': {'activeQuestionMutations': 1}})
    assert client.delete(base + '/' + target['id'], headers=owner).status_code == 409
    db.surveys.update_one({'_id': ObjectId(survey['id'])}, {'$set': {'activeQuestionMutations': 0}})
    assert client.delete(base + '/' + target['id'], headers=owner).status_code == 204
