# 基于 MongoDB 的在线问卷系统

本仓库为课程项目第二阶段提交仓库：[survey-system-phase2](https://github.com/chenyunshu1031/survey-system-phase2)。第一阶段仓库为[survey-system-phase1](https://github.com/chenyunshu1031/survey-system-phase1)，阶段二保留其基线提交`1aa9b3804295ccfe44783b64b7993f798725302e`及历史，在原代码基础上扩展。Word报告单独提交；第二阶段测试用例、AI使用日志及引用的浏览器截图保存在`docs/`中。

本项目实现问卷创建、发布、填写和结果统计。注册用户可以管理自己的问卷，通过链接邀请其他用户登录作答；后端根据题目配置校验答案、执行条件跳转，并将答卷保存到 MongoDB。

## 功能

- 账号注册、登录、密码哈希存储及问卷管理权限检查。
- 创建和编辑问卷，设置说明、匿名展示、重复填写和截止时间，发布或关闭问卷。
- 单选、多选、文本和数字四种题型，支持必答、选择数量、文本长度及数字范围限制。
- 单选、多选和数字条件跳转，按优先级执行第一条命中的规则，未命中则进入下一题。
- 逐题填写、返回改答、后端答题路径复核及重复提交限制。
- 整份和单题统计，包括选项计数、到达与回答人数、原始填写内容及数字平均值。
- 个人题库可创建、改名和移除；可直接创建可复用题目，或将本人旧问卷题目显式保存供以后选用。版本历史可追溯，恢复旧内容时新增版本，题库条目固定选定版本。
- 按用户名分享题目、撤销分享，在草稿问卷中选入指定版本并查看使用关系。
- 问卷实例保存内容快照；逻辑题目所有者可自动查看所有有效来源问卷的聚合统计。版本单独展示，内容完全相同的版本可合并展示；数字题显示均值与区间分布，文本仅显示达到五名不同填写者门槛的重复答案，小样本结果会抑制。

“所有问卷”只包括实际选入同一可复用题目版本且来源快照有效的问卷。第一阶段旧题目不会凭题干相同自动归并；显式保存旧题也不追溯改写旧答卷。旧版按问卷所有者授权统计的接口仍保留供旧客户端使用，当前页面使用自动汇总接口。

填写者必须登录。匿名提交在统计中隐藏账号，数据库保留身份用于执行重复填写限制。未提交答案仅保存在当前页面，刷新后清空。

## 技术与目录

| 目录 | 内容 |
| --- | --- |
| `backend/app/` | FastAPI 接口、Pydantic 模型、PyMongo 数据访问及业务逻辑 |
| `backend/app/db/schema.py` | MongoDB 集合校验规则及索引 |
| `backend/tests/` | 后端自动测试和真实 MongoDB 集成测试 |
| `frontend/src/` | Vue 3、TypeScript、Vue Router、Pinia 页面及交互 |
| `frontend/tests/` | 会话、时间、答案校验和跳转逻辑测试 |
| `docs/` | 设计、接口、测试、截图及 AI 使用日志 |

所有业务数据存储于 MongoDB。前后端使用通用开发框架，问卷业务由项目代码实现。

## 本地运行

### 本机一键启动

2026-10-27已将第二阶段切换到原业务库`127.0.0.1:27017/survey_system`，数据目录为`backend/.local-mongo-data`。在项目目录执行：

**当前状态：**题库改名／归档、旧问卷题目保存和自动跨问卷汇总代码已接入原业务库服务。更新前正常关库制作并逐文件校验离线备份；重启后旧四集合的数量、ID和内容哈希一致，当前校验器、索引及新增API路由已核对。新增业务流程在隔离MongoDB与浏览器验证，本轮未向原业务库写入测试答卷。记录见[本轮更新记录](docs/phase2-auto-scope-upgrade.md)。

```powershell
.\start-local.ps1
```

脚本会核对MongoDB的数据目录，启动单进程后端和前端，并在服务已由该脚本启动时复用原进程。访问`http://127.0.0.1:5173/`，使用原账号登录。日志和进程记录位于`tmp/local-runtime/`；前端来源配置应为`http://127.0.0.1:5173`。本脚本使用本机Python3.13及已安装的`backend/.deps`，其他电脑请按下文安装依赖。

本次切换保留原四集合的7／8／24／11条记录，新增六个题库及授权集合；临时验收数据已清理。备份、验证和回退说明见[第二阶段本机切换记录](docs/phase2-cutover.md)。以下为手工安装和运行方法。

环境要求：Python 3.12+、Node.js 20.19+ 或 22.12+、MongoDB 7/8。先启动 MongoDB，默认连接 `mongodb://127.0.0.1:27017`。前后端分别在两个终端运行。

### 1. 后端

进入 `backend` 目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

首次配置时复制 `.env.example`；已有 `.env` 时保留现有配置。按实际环境设置：

| 配置 | 含义 | 默认示例 |
| --- | --- | --- |
| `MONGODB_URI` | 数据库连接地址 | `mongodb://127.0.0.1:27017` |
| `MONGODB_DB` | 业务数据库 | `survey_system` |
| `JWT_SECRET` | 登录令牌签名密钥 | 替换为足够长的随机字符串 |
| `JWT_EXPIRE_MINUTES` | 令牌有效分钟数 | `120` |
| `FRONTEND_ORIGIN` | 允许的前端来源 | `http://localhost:5173` |

启动后端：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口页面：`http://127.0.0.1:8000/docs`。启动时初始化原四集合及六个新增集合的校验规则和索引；旧题目不自动合并，旧答卷不改写。

### 2. 前端

进入 `frontend` 目录执行：

```powershell
npm ci
npm run dev -- --port 5173 --strictPort
```

访问 `http://localhost:5173/surveys`，注册并登录。开发服务器将 `/api` 请求代理至 `http://127.0.0.1:8000`。

若 5173 已被其他程序占用，前端可改用空闲端口，例如：

```powershell
npm run dev -- --port 5174 --strictPort
```

对应访问 `http://localhost:5174/surveys`，并将后端 `FRONTEND_ORIGIN` 设为 `http://localhost:5174` 后重启后端。验收截图使用的是 5174 端口。

### 3. 运行约束

后端按单个服务进程运行。问卷文档中的活动计数协调发布与编辑、关闭与提交；冲突返回 409，重新读取后可重试。异常退出留下的计数在下次单进程启动时恢复。

发布后锁定题目、跳转规则、匿名和重复设置，标题、说明及截止时间仍可调整。时间按 UTC 存储，页面统一使用北京时间。

## 测试

后端在 `backend` 目录执行：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

常规接口测试使用 mongomock。真实 MongoDB 测试默认跳过，启用前先确认测试实例可连接：

```powershell
$env:RUN_MONGO_INTEGRATION = '1'
$env:MONGO_TEST_URI = 'mongodb://127.0.0.1:27018'
python -m pytest -q
```

端口按实际实例调整；测试仅操作随机命名的 `survey_system_test_*` 数据库，结束后清理。

前端在 `frontend` 目录执行：

```powershell
npm test
npm run build
```

2026-10-21 的完整后端测试为 64 passed、0 skipped，其中 3 项使用真实 MongoDB；前端 8 个测试项通过，TypeScript 检查与 Vite 构建成功。浏览器手工验收 H01—H08 通过，包含 13 张代表截图。本机独立环境已完成依赖安装及启动、发布、提交、统计流程验证。

2026-10-27切换前重新执行后端完整测试：101通过、0失败、0跳过，真实数据库测试使用独立29143实例；前端12项通过，类型检查和生产构建通过。切换后另在原库执行101次真实HTTP请求，核对8份旧问卷和24道旧题的读取与统计，并验证新增功能；随后按本轮临时ID清理验收数据，原四集合ID与完整内容哈希均未改变。该HTTP检查与自动测试是两份独立证据。

## 文档

| 文档 | 内容 |
| --- | --- |
| [系统与数据库设计](docs/design.md) | 集合划分、索引、跳转、校验、状态及统计逻辑 |
| [API 说明](docs/api.md) | 路径、请求字段、返回示例及错误状态 |
| [测试用例与结果](docs/test-cases.md) | 自动测试及手工验收的步骤、输入、输出和结果 |
| [手工验收截图](docs/manual-screenshots-20261021.md) | 13 张截图及用例对应关系 |
| [第一阶段AI使用日志](docs/ai-collaboration.md) | 25项开发记录、任务指令、生成代码、修改及验证结果 |
| [第二阶段测试用例与结果](docs/phase2-test-cases.md) | 新需求、原功能回归、旧数据兼容及完整页面填写测试 |
| [第二阶段AI使用日志](docs/phase2-ai-collaboration.md) | 19项协作记录，包含需求选择、Prompt、代码产出和验收推动的修改 |
| [第二阶段本人手工测试截图](docs/images/phase2-manual/README.md) | 题库、版本、发布、使用追踪和撤销分享等13张截图 |

## 第一阶段交付

- [交付文件与实验要求逐项对照](docs/submission.md)
- GitHub 仓库：[chenyunshu1031/survey-system-phase1](https://github.com/chenyunshu1031/survey-system-phase1)（私有）

提交目录包含代码、MongoDB schema、配置示例、正式说明、测试用例、验收截图和 AI 使用日志。Word 报告单独提交，不上传仓库。本地数据库、实际 `.env`、依赖目录、日志、旧报告及生成预览不纳入仓库。
