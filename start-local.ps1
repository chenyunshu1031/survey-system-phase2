param()
$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$backend = Join-Path $project 'backend'
$frontend = Join-Path $project 'frontend'
$data = Join-Path $backend '.local-mongo-data'
$runtime = Join-Path $project 'tmp\local-runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $backend '.env'))) { throw 'backend/.env is required.' }
if (-not (Test-Path -LiteralPath (Join-Path $data 'WiredTiger'))) { throw 'Original project MongoDB data directory is missing.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules\vite\bin\vite.js'))) { throw 'Install frontend dependencies with npm ci first.' }
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$node = (Get-Command node -ErrorAction Stop).Source
$mongod = (Get-Command mongod -ErrorAction Stop).Source
$stateFile = Join-Path $runtime 'processes.json'
$prior = if (Test-Path -LiteralPath $stateFile) { Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }

function Listening([int]$port) {
    return @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}
function Wait-Listening([int]$port) {
    for ($i=0; $i -lt 30; $i++) {
        if (Listening $port) { return }
        Start-Sleep -Milliseconds 300
    }
    throw "Port $port did not start; inspect logs in $runtime"
}
function Existing-OwnedProcess([int]$port, $recordedPid) {
    $listeners=Listening $port
    if (-not $listeners) { return $false }
    if ($null -ne $recordedPid -and @($listeners | Where-Object {$_.OwningProcess -eq [int]$recordedPid}).Count -gt 0) { return $true }
    throw "Port $port is occupied by an unrecognized process; no process was stopped."
}

$env:PYTHONPATH = Join-Path $backend '.deps'
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017'
$env:MONGODB_DB = 'survey_system'
$env:FRONTEND_ORIGIN = 'http://127.0.0.1:5173'
if (-not (Listening 27017)) {
    $mongo = Start-Process -FilePath $mongod -ArgumentList @('--dbpath',('"'+$data+'"'),'--bind_ip','127.0.0.1','--port','27017','--logpath',('"'+(Join-Path $runtime 'mongodb.log')+'"'),'--logappend') -WindowStyle Hidden -PassThru
    Wait-Listening 27017
}
# Verify that an existing listener is this project's original database.
& $python -c 'from pathlib import Path; import sys; from pymongo import MongoClient; c=MongoClient("mongodb://127.0.0.1:27017",serverSelectionTimeoutMS=5000); p=c.admin.command("getCmdLineOpts")["parsed"]; assert str(Path(p["storage"]["dbPath"]).resolve()).casefold()==str(Path(sys.argv[1]).resolve()).casefold(), "27017 is not the project data directory"; c.close()' $data
if ($LASTEXITCODE -ne 0) { throw 'MongoDB instance verification failed.' }
$backendPid = if ($prior) { $prior.backendPid } else { $null }
if (-not (Existing-OwnedProcess 8000 $backendPid)) {
    $api = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'backend.out.log') -RedirectStandardError (Join-Path $runtime 'backend.err.log') -PassThru
    $backendPid = $api.Id
    Wait-Listening 8000
}
$frontendPid = if ($prior) { $prior.frontendPid } else { $null }
if (-not (Existing-OwnedProcess 5173 $frontendPid)) {
    $web = Start-Process -FilePath $node -ArgumentList @(('"'+(Join-Path $frontend 'node_modules\vite\bin\vite.js')+'"'),'--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'frontend.out.log') -RedirectStandardError (Join-Path $runtime 'frontend.err.log') -PassThru
    $frontendPid = $web.Id
    Wait-Listening 5173
}
$schema = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 10
if ($null -eq $schema.paths.'/api/v1/library/questions') { throw 'The running API does not expose phase-two endpoints.' }
$page = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -TimeoutSec 10
if ($page.StatusCode -ne 200) { throw 'Frontend health check failed.' }
@{backendPid=$backendPid;frontendPid=$frontendPid;mongoPid=(Listening 27017)[0].OwningProcess;mongodbUri=$env:MONGODB_URI;database=$env:MONGODB_DB;dataDirectory=$data;frontendUrl='http://127.0.0.1:5173/';verifiedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
Write-Output 'Ready: http://127.0.0.1:5173/'
Write-Output 'Database: 127.0.0.1:27017/survey_system (original project directory)'
