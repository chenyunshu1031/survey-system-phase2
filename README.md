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

“所有问卷”只包括实际选入同一可复用题目版本且来源快照有效的问卷。第一阶段旧题目不会凭题干相同自动归并；显式保存旧题也不追溯改写旧答卷。阶段二早期实现的按问卷授权统计接口仍保留供相应客户端使用，当前页面使用自动汇总接口；该授权接口并非第一阶段原有功能。

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

新电脑首次运行可以使用空MongoDB，按下方“后端”“前端”步骤安装依赖、配置并启动。后端初始化会创建集合校验器和索引，不需要取得本机的物理数据目录或恢复历史备份。恢复第一阶段备份只用于复现历史数据兼容检查。

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

对应访问 `http://localhost:5174/surveys`，并将后端 `FRONTEND_ORIGIN` 设为 `http://localhost:5174` 后重启后端。历史截图使用不同隔离端口，以各次执行记录标注为准。

### 3. 运行约束

后端按单个服务进程运行。问卷文档中的活动计数协调发布与编辑、关闭与提交；冲突返回 409，重新读取后可重试。异常退出留下的计数在下次单进程启动时恢复。

发布后锁定题目、跳转规则、匿名和重复设置，标题、说明及截止时间仍可调整。时间按 UTC 存储，页面统一使用北京时间。

### 4. 本机原库启动（可选）

`start-local.ps1`用于本机已有环境，要求原`backend/.local-mongo-data`目录、`backend/.env`、`backend/.deps`和前端依赖存在。它检查27017数据目录并启动或复用8000、5173服务，不是新电脑首次安装脚本。运行中的后端若仍为旧代码，应在核对进程归属后重启，不以网页能打开代替版本验证。

```powershell
.\start-local.ps1
```

首次结构切换及随后更新的历史结果见[部署与兼容记录](docs/evidence/phase2/deployment/auto-scope-upgrade.md)。备份和物理数据目录保留在本地，不随代码发布。

## 测试

后端在已安装依赖的虚拟环境中运行：

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

普通命令使用模拟库，5项真实MongoDB集成测试默认跳过。复现完整回归时，先启动独立MongoDB8.3.11实例（本组真实库测试有版本断言），再设置：

```powershell
$env:RUN_MONGO_INTEGRATION = '1'
$env:MONGO_TEST_URI = 'mongodb://127.0.0.1:29149'
$env:RUN_LIBRARY_MONGO_INTEGRATION = '1'
$env:LIBRARY_MONGO_TEST_URI = 'mongodb://127.0.0.1:29149'
$env:MONGODB_URI = 'mongodb://127.0.0.1:29149'
$env:MONGODB_DB = 'phase2_final_evidence'
$env:FRONTEND_ORIGIN = 'http://localhost:5173'
python -m pytest -q
```

不要将上述测试地址替换为原业务库。真实库用例创建随机命名的测试库，结束后清理。独立空库启动方法、实际执行命令及退出码见[完整回归原始记录](docs/evidence/phase2/regression-20261028/README.md)。

前端在frontend目录执行：

```powershell
npm test
npm run build
```

最新完整回归：后端109通过、0失败、0跳过，其中5项使用真实MongoDB，其余104项为模拟库及其他测试；前端12通过，类型检查和生产构建成功。浏览器验收区分本人手工操作与AI辅助执行，步骤、输入输出及截图见下列文档。历史批次与当前结果分别记录，不重复相加。

## 第二阶段提交文档

| 材料 | 内容 |
| --- | --- |
| [系统与数据库设计](docs/phase2-design.md) | 扩展架构、集合与引用、嵌入和快照、权限、版本、跳转、校验、统计及兼容 |
| [API说明](docs/api.md) | 第一阶段保留接口及第二阶段新增接口、字段、错误状态 |
| [测试用例与结果](docs/phase2-test-cases.md) | P2-01—P2-21的步骤、输入、预期、实际输出、结果和证据 |
| [浏览器截图图集](docs/phase2-browser-screenshots.md) | 25张代表截图及执行方式、用例对应关系 |
| [完整回归原始输出](docs/evidence/phase2/regression-20261028/README.md) | 代码提交号、命令、环境、退出码、pytest与前端输出 |
| [AI使用日志与说明](docs/phase2-ai-collaboration.md) | 19项Prompt与产出、修改记录，以及AI帮助、AI问题、本人修改和本人设计 |
| [MongoDB schema](backend/app/db/schema.py) | 集合校验器和索引定义 |
| [配置示例](backend/.env.example) | 无真实密钥的环境变量模板 |

### 第一阶段基线与回归依据

保留[原系统设计](docs/design.md)、[T01—T22测试用例](docs/test-cases.md)、[第一阶段截图](docs/manual-screenshots-20261021.md)与[第一阶段AI日志](docs/ai-collaboration.md)，供核对扩展前结构与旧功能回归。第一阶段仓库：[survey-system-phase1](https://github.com/chenyunshu1031/survey-system-phase1)（公开）。
