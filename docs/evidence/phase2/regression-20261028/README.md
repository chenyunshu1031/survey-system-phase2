# 第二阶段完整回归原始记录

本批次在2026-10-28T19:54:58.397420+08:00执行，对应代码提交`eb89d02ae450aa7d26565bede479d0ea44c9cc5d`。后端源码树为`8270c3b9c947cdeb85639caa503bb03f3a2cced6`。本轮整理证据与说明文档，没有修改产品代码；已有浏览器操作不在本轮重复记作新验收。

## 环境与隔离范围

新建空MongoDB8.3.11数据目录，仅绑定127.0.0.1:29149。所有真实库测试使用该端口下的随机测试库；未连接27017原业务库，也未读写第一阶段备份。测试结束后随机业务测试库均已清理，独立MongoDB正常关闭。配置、命令、退出码与文件哈希见[执行元数据](execution.json)。

## 执行结果

| 检查 | 结果 | 原始输出 |
| --- | --- | --- |
| 后端完整回归 | 109通过、0失败、0错误、0跳过；其中真实MongoDB5项，其余104项 | [pytest日志](backend-pytest.txt)、[JUnit结果](backend-junit.xml) |
| 前端测试 | 12通过、0失败、0跳过 | [Node测试日志](frontend-tests.txt) |
| TypeScript类型检查 | 退出码0 | [类型检查日志](frontend-typecheck.txt) |
| Vite生产构建 | 退出码0 | [构建日志](frontend-build.txt) |

类型检查成功时没有标准输出，原始日志为空文件；以execution.json记录的命令退出码为准。前端答题工具另报告48项内部断言，不与12个测试项相加。历史原库101次HTTP请求也是独立记录，不与109项pytest测试相加。

## 复现命令

先在独立终端启动本轮专用端口的MongoDB，数据目录使用新建的空目录；不要替换为27017业务库。以下步骤中的隔离目录位于项目忽略的tmp目录，不作为交付数据。

```powershell
# 项目根目录；首次复现时建立新的空目录
New-Item -ItemType Directory -Path .\tmp\regression-empty-mongo -ErrorAction Stop
mongod --dbpath .\tmp\regression-empty-mongo --bind_ip 127.0.0.1 --port 29149
```

在已按README安装依赖的后端环境中执行：

```powershell
cd backend
$env:RUN_MONGO_INTEGRATION = '1'
$env:MONGO_TEST_URI = 'mongodb://127.0.0.1:29149'
$env:RUN_LIBRARY_MONGO_INTEGRATION = '1'
$env:LIBRARY_MONGO_TEST_URI = 'mongodb://127.0.0.1:29149'
$env:MONGODB_URI = 'mongodb://127.0.0.1:29149'
$env:MONGODB_DB = 'phase2_final_evidence'
$env:FRONTEND_ORIGIN = 'http://localhost:5173'
python -m pytest -q --junitxml=../docs/evidence/phase2/regression-20261028/backend-junit.xml
```

本机实际使用项目.venv的Python并将backend/.deps加入PYTHONPATH。换机时按README安装到自己的虚拟环境即可，不依赖该本机目录。真实库测试含MongoDB8.3.11版本断言，复现本组测试应使用相同版本。

前端在frontend目录执行：

```powershell
npm test
npx vue-tsc -b
npx vite build
```

本轮使用Node直接调用同一套测试文件、vue-tsc和Vite入口，实际命令逐项记录在execution.json中。npm run build本身包含类型检查与构建，也可用于常规验证。

## 警告说明

pytest输出两条警告：Starlette/httpx的接口弃用提示，以及构造异常算法令牌的测试密钥长度提示。两者均完整保留在原始日志中，未产生失败或跳过项；不能将此测试用密钥长度提示视为生产密钥配置已经通过检查。
