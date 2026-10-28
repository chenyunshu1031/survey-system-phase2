# 第一阶段 API 说明

## 一、调用约定

基础路径：`/api/v1`。请求和响应均为 JSON；除注册、登录外需要 `Authorization: Bearer <accessToken>`。接口文档也可由运行中的后端 `/docs` 查看。

## 二、接口列表

| 方法与路径 | 用途 | 主要请求字段 |
| --- | --- | --- |
| `POST /auth/register` | 注册，201 | `username`, `password` |
| `POST /auth/login` | 登录 | `username`, `password`；返回 `accessToken` |
| `GET /auth/me` | 当前账号 | 无 |
| `POST /surveys` | 创建草稿问卷，201 | `title`, `description?`, `allowAnonymous?`, `allowMultipleSubmissions?`, `deadlineAt?` |
| `GET /surveys` | 列出本人问卷 | 无 |
| `GET /surveys/{surveyId}` | 读取本人问卷 | 无 |
| `PATCH /surveys/{surveyId}` | 更新问卷配置 | 上述可变字段，按提交字段更新 |
| `POST /surveys/{surveyId}/questions` | 在草稿中追加题目，201 | `type`, `title`, `required?`, `options?`, `validation?` |
| `GET /surveys/{surveyId}/questions` | 按顺序读取题目 | 无 |
| `PUT /surveys/{surveyId}/questions/{questionId}` | 完整更新本人草稿问卷中的题目 | `type`, `title`, `required`, `options`, `validation` |
| `PUT /surveys/{surveyId}/questions/{questionId}/jump-rules` | 保存该题的有序跳转规则，仅草稿可用 | `rules` 数组，见下方说明 |
| `POST /surveys/{surveyId}/publish` | 发布草稿问卷 | 无请求体；至少一题且截止时间未过 |
| `POST /surveys/{surveyId}/close` | 关闭已发布问卷 | 无请求体 |
| `GET /public/surveys/{slug}` | 已登录用户按链接读取已发布或已关闭问卷 | 无；返回公开配置、题目及当前账号的 `hasSubmitted` |
| `POST /public/surveys/{slug}/responses` | 按路径提交完整答卷，201 | `isAnonymous?`、按访问顺序排列的 `answers` |
| `GET /surveys/{surveyId}/statistics` | 创建者查看整份问卷统计 | 返回答卷总数、逐题统计、时间上界 `asOf` 和提交版本 `submissionRevision`；文本和数字内容每题先返回最多 100 条 |
| `GET /surveys/{surveyId}/statistics/questions/{questionId}` | 创建者查看单题统计及后续内容 | 可选 `offset`（从 0 起）、`limit`（1–100）、`asOf`、`submissionRevision`；持续分页须携带首次返回的时间与版本，版本参数不能单独使用 |

## 三、问卷与题目配置

`type` 为 `single`、`multiple`、`text`、`number`。选择题的 `options` 是至少两个不重复的选项文字；返回后每个选项含稳定 `id`。多选可设 `validation.minSelections`、`maxSelections`；文本可设 `minLength`、`maxLength`；数字可设 `minValue`、`maxValue`、`integerOnly`。最小值不能大于最大值，且不同题型不能混用规则。日期采用带时区的 ISO 8601，设置时须为未来时间；数据库按 UTC 存储，接口响应带 UTC 时区标记，网页按北京时间（UTC+8）输入和显示。

更新题目时，`options` 改为对象数组，例如 `[{"id":"原选项ID","label":"修改后的文字"},{"label":"新增选项"}]`。保留原选项 ID 可让后续跳转规则稳定引用；新增选项省略 ID，由服务端生成。若题型、选项或校验规则改变，当前题目的跳转规则会清空，之后应重新配置。已发布或已关闭的问卷不允许更新题目。

问卷设置更新、题目修改和规则保存通过内部 `configurationRevision` 检查请求执行期间的变化；发布也检查配置版本。有冲突时返回 409，调用者重新读取后重试。该字段由后端维护，缺少字段的旧问卷按 0 兼容。

多选题创建请求示例：

```json
{
  "type": "multiple",
  "title": "你喜欢的水果？",
  "required": true,
  "options": ["苹果", "香蕉", "西瓜"],
  "validation": {"minSelections": 2, "maxSelections": 3}
}
```

## 四、跳转规则

跳转规则以 `rules` 数组整体保存，每条含 `priority`（从 1 起，不能重复）、`targetQuestionId` 和 `operator`；更新已有规则时可携带其 `id`。单选使用 `equals`，`optionIds` 数组只含一个选项 ID；多选使用 `containsAny` 或 `containsAll` 与非空 `optionIds`；数字使用 `eq`、`gt`、`gte`、`lt`、`lte` 配 `value`，或 `between` 配 `minValue`、`maxValue`（含边界）。目标必须是本问卷的后续题目，文本题不能设条件跳转。服务端按优先级先后匹配，未命中则按顺序进入下一题；提交答卷时重新计算路径。

保存跳转规则时还会检查单条条件在题目的数值范围、整数要求或多选数量限制下是否可能命中；不可能命中的条件返回 422，原规则不被覆盖。发布时也复核此条件。创建者读取、添加、修改题目或保存规则的响应包含派生字段 `jumpRuleWarnings`（字符串数组），用于提示部分重叠、前置规则完全覆盖或复杂组合分析未完成；这些提示不阻止保存，也不写入数据库或返回给填写者。数字覆盖分析考虑严格比较边界，多选覆盖分析使用有计算上限的约束搜索；达到上限时提示试填验证，不把未完成分析判为通过。

## 五、发布与答卷提交

问卷响应中的 `status` 是持久化状态（`draft`、`published`、`closed`）；`availability` 是派生状态（`draft`、`open`、`expired`、`closed`）。发布后锁定题目、跳转规则、匿名与重复填写设置；标题、说明和截止时间仍可修改。`GET /public/surveys/{slug}` 在未登录时返回 401，草稿或不存在时返回 404；对已截止或关闭的问卷仍返回内容及相应 `availability`。网页路径 `/survey/{slug}` 在开放时提供逐题填写，到期或关闭后只展示内容。

发布复核存储类型、选项及规则标识，异常配置返回 409；最终写入再次检查截止时间。文本答案在前后端按相同空白集合去首尾空白；空数组仅表示多选留空。计数限制和 `priority` 不超过 9,007,199,254,740,991。

答卷请求示例：

```json
{
  "isAnonymous": true,
  "answers": [
    {"questionId": "第一题ID", "value": "选项ID"},
    {"questionId": "跳转后的题目ID", "value": ["选项ID一", "选项ID二"]},
    {"questionId": "最后一题ID", "value": null}
  ]
}
```

`answers` 必须包含实际到达的每道题，按答题顺序排列；被跳过的题不得出现。单选值为选项 ID，多选为选项 ID 数组，文字为字符串，数字为 JSON 数字；未回答的选答题可用 `null`（多选也可用空数组）。成功返回答卷 `id`、`submittedAt`、`isAnonymous`，不返回账户 ID。未登录为 401；已截止、关闭或不允许重复提交为 409；题目答案、路径或匿名设置不合法为 422。`responses` 中仍保存账户 ID 以执行重复填写约束，统计展示时需遵循匿名设置。

## 六、统计

统计接口只允许问卷创建者读取，其他登录用户得到 404。整份问卷结果返回 `responseCount`、时间上界 `asOf`、提交版本 `submissionRevision` 和逐题 `questions`；每题有 `reachedCount`、`answeredCount`。单选和多选的 `optionCounts` 保留所有选项，包括零票选项；多选按每个选项被选中的次数计数。文本和数字题的 `entries` 每次最多返回 100 条非空答案、提交时间和展示身份，`hasMoreEntries` 表示是否还有后续内容。

继续分页携带首次返回的 `asOf` 和 `submissionRevision`；若有提交正在进行，或扫描、分页之间提交版本改变，接口返回 409，页面提示刷新。提交尝试即递增版本，失败的提交也可能触发刷新。只携带 `asOf` 的旧调用可读取时间范围内数据，但不执行跨页版本检查。

匿名答卷显示“匿名”，不返回账户 ID 或用户名。数字题的 `average` 根据全部有效答案计算，无数字答案时为 `null`。选答留空计入到达人数，不计入回答人数；跳过题目两者都不计入。

题目保存与发布、答卷提交与关闭之间通过问卷记录中的活动计数协调：若有题目正在保存，发布返回 409；若有答卷正在提交，关闭返回 409，稍后重试即可。此机制针对 README 所述的单服务进程本地运行方式；若第二阶段改为多进程或多实例部署，需要改用副本集事务或带租约的跨实例协调机制。

## 七、错误状态

| 状态码 | 含义 |
| --- | --- |
| 401 | 未登录或令牌失效 |
| 404 | 资源不存在、未发布或不属于当前用户 |
| 409 | 用户名、问卷状态、配置版本、重复提交等冲突 |
| 413 | 写入内容超过 MongoDB 单文档上限，未保存失败答卷 |
| 422 | 字段、规则或答案不合法 |

前端显示接口错误提示，是否接受请求由后端校验决定。

## 八、第二阶段新增接口

以下路径省略`/api/v1`前缀，均要求登录。创建题库、逻辑题目、版本、恢复和旧题保存使用`Idempotency-Key`；同一键和同一内容重试返回已有结果，键与内容不匹配返回409。

| 类别 | 方法与路径 | 说明 |
| --- | --- | --- |
| 题库 | `POST/GET /question-banks`；`PATCH/DELETE /question-banks/{id}` | 创建、列出、改名、归档个人题库；归档不删除题目和版本 |
| 题库条目 | `GET/POST /question-banks/{id}/items`；`PUT /question-banks/{id}/items/{qid}/version`；`DELETE /question-banks/{id}/items/{qid}` | 加入题目、固定或显式切换版本、移除条目 |
| 可复用题目 | `POST/GET /library/questions`；`GET /library/questions/{qid}` | 创建、列出、读取逻辑题目 |
| 历史版本 | `GET/POST /library/questions/{qid}/versions`；`POST /library/questions/{qid}/versions/{vid}/restore` | 查看历史、基于指定版本创建新版、将旧内容复制为新版本 |
| 分享与追踪 | `POST/GET /library/questions/{qid}/shares`；`DELETE /library/questions/{qid}/shares/{recipientId}`；`GET /library/shared/questions`；`GET /library/questions/{qid}/usages` | 按用户名分享、撤销、查看获分享题目与最小使用关系 |
| 选题与旧题保存 | `POST /surveys/{id}/questions/from-library`；`POST /surveys/{id}/questions/{qid}/save-to-library` | 草稿选入指定版本；将本人旧问卷题目显式保存供今后复用 |
| 草稿题目删除 | `DELETE /surveys/{id}/questions/{questionId}` | 仅问卷所有者可删除草稿实例，成功返回204；其他题的跳转规则指向此题时返回409，须先调整规则。保留题库原题、历史版本及其他实例的ID和顺序 |
| 自动统计 | `GET /library/questions/{qid}/versions/{vid}/all-survey-statistics`；`GET /library/questions/{qid}/all-survey-statistics` | 作者查看所有有效来源问卷的单版聚合及同内容版本分组总览 |

自动统计不要求问卷所有者另行授权，但只向逻辑题目作者提供聚合结果。单版结果按每份答卷去重，数字题按答卷等权并给区间分布；文本只显示至少5名不同填写者给出的相同答案。任一非零答卷层面指标或数字区间少于5名不同填写者时，相关答卷层面字段返回`null`并标记`suppression.applied=true`。总览仅合并题型、题干、必答、选项及其ID、校验配置完全一致的版本。第一阶段旧题没有来源关系，不自动纳入。

为兼容先前客户端，`GET/PUT/DELETE /surveys/{id}/cross-survey-statistics/{qid}/consent`及`GET /library/questions/{qid}/versions/{vid}/cross-survey-statistics`仍可调用。旧路径按问卷所有者授权范围计算，与当前页面使用的自动统计路径口径不同。
