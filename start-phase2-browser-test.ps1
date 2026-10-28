$ErrorActionPreference='Stop'
$project=$PSScriptRoot
$backend=Join-Path $project 'backend'
$frontend=Join-Path $project 'frontend'
$data=Join-Path $project 'tmp\unit6-fresh-719cbebfc441447fadbdcd3a827bca94'
$runtime=Join-Path $project 'tmp\phase2-browser-test-runtime'
$mongoPort=29141
$apiPort=18000
$webPort=15173
$mongoExe='D:\bin\mongod.exe'
$python=Join-Path $project '.venv\Scripts\python.exe'
$node=(Get-Command node -ErrorAction Stop).Source
if(-not(Test-Path -LiteralPath (Join-Path $data 'WiredTiger'))){throw 'The isolated unit6 data directory is missing.'}
if(-not(Test-Path -LiteralPath $mongoExe)){throw 'mongod.exe is missing.'}
if(-not(Test-Path -LiteralPath $python)){throw 'Project Python environment is missing.'}
if(-not(Test-Path -LiteralPath (Join-Path $frontend 'node_modules\vite\bin\vite.js'))){throw 'Frontend dependencies are missing.'}
New-Item -ItemType Directory -Path $runtime -Force|Out-Null
$statePath=Join-Path $runtime 'processes.json'
$prior=if(Test-Path -LiteralPath $statePath){Get-Content -LiteralPath $statePath -Raw -Encoding utf8|ConvertFrom-Json}else{$null}
function Listener([int]$port){@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)}
function Wait-Listener([int]$port){for($i=0;$i -lt 40;$i++){if(Listener $port){return};Start-Sleep -Milliseconds 300};throw "Port $port did not open."}
function Known-Listener([int]$port,$savedPid){
 $items=Listener $port
 if(-not $items){return $false}
 if($null -ne $savedPid -and @($items|Where-Object{$_.OwningProcess -eq [int]$savedPid}).Count -gt 0){return $true}
 throw "Port $port is occupied by an unrecognized process; no process was stopped."
}
$mongoPid=if($prior){$prior.mongoPid}else{$null}
if(-not(Listener $mongoPort)){
 $mongo=Start-Process -FilePath $mongoExe -ArgumentList @('--dbpath',('"'+$data+'"'),'--bind_ip','127.0.0.1','--port',"$mongoPort",'--logpath',('"'+(Join-Path $runtime 'mongodb.log')+'"'),'--logappend') -WindowStyle Hidden -PassThru
 $mongoPid=$mongo.Id
 Wait-Listener $mongoPort
}
$env:PYTHONPATH=Join-Path $backend '.deps'
$env:MONGODB_URI="mongodb://127.0.0.1:$mongoPort"
$env:MONGODB_DB='unit6_browser'
$env:FRONTEND_ORIGIN="http://127.0.0.1:$webPort"
& $python -c 'from pathlib import Path; from pymongo import MongoClient; import sys; c=MongoClient(sys.argv[1],serverSelectionTimeoutMS=3000); opts=c.admin.command("getCmdLineOpts")["parsed"]; actual=Path(opts["storage"]["dbPath"]).resolve(); expected=Path(sys.argv[2]).resolve(); assert str(actual).casefold()==str(expected).casefold(), "Unexpected MongoDB data path"; print("Isolated MongoDB verified")' $env:MONGODB_URI $data
if($LASTEXITCODE -ne 0){throw 'MongoDB path verification failed.'}
$mongoPid=(Listener $mongoPort)[0].OwningProcess
$apiPid=if($prior){$prior.apiPid}else{$null}
if(-not(Known-Listener $apiPort $apiPid)){
 $api=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$apiPort") -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'api.out.log') -RedirectStandardError (Join-Path $runtime 'api.err.log') -PassThru
 $apiPid=$api.Id
 Wait-Listener $apiPort
 $apiPid=(Listener $apiPort)[0].OwningProcess
}
$webPid=if($prior){$prior.webPid}else{$null}
if(-not(Known-Listener $webPort $webPid)){
 $web=Start-Process -FilePath $node -ArgumentList @(('"'+(Join-Path $frontend 'node_modules\vite\bin\vite.js')+'"'),'--host','127.0.0.1','--port',"$webPort",'--strictPort','--config','vite.browser-test.config.ts') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'web.out.log') -RedirectStandardError (Join-Path $runtime 'web.err.log') -PassThru
 $webPid=$web.Id
 Wait-Listener $webPort
 $webPid=(Listener $webPort)[0].OwningProcess
}
$spec=Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/openapi.json" -TimeoutSec 10
if($null -eq $spec.paths.'/api/v1/library/questions'){throw 'Stage-two API route missing.'}
$page=Invoke-WebRequest -Uri "http://127.0.0.1:$webPort/" -TimeoutSec 10
if($page.StatusCode -ne 200){throw 'Frontend failed.'}
@{mongoPid=$mongoPid;apiPid=$apiPid;webPid=$webPid;dataDirectory=$data;mongoUri=$env:MONGODB_URI;db=$env:MONGODB_DB;url="http://127.0.0.1:$webPort/";verifiedAt=(Get-Date).ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath $statePath -Encoding utf8
Write-Output "Isolated browser test ready: http://127.0.0.1:$webPort/"
Write-Output "Database: 127.0.0.1:$mongoPort/unit6_browser"






