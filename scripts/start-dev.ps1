param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "front"
$Logs = Join-Path $Root "logs"
$LocalPython = Join-Path $Root ".venv-rqsdk\Scripts\python.exe"
$env:PYTHONDONTWRITEBYTECODE = "1"

New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Stop-PortProcess {
  param([int]$Port)
  $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($connection in $connections) {
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    if ($process) {
      Stop-Process -Id $process.Id -Force
      Start-Sleep -Milliseconds 500
    }
  }
}

if (Test-Path $LocalPython) {
  $Python = $LocalPython
} else {
  $PyCommand = Get-Command py -ErrorAction SilentlyContinue
  if ($PyCommand) {
    $Python = $PyCommand.Source
    $PythonLauncherVersion = "-3.12"
  } else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
      $Python = $PythonCommand.Source
    }
  }
}

if (!$Python) {
  throw "Python runtime not found. Create .venv-rqsdk or install Python and make it available in PATH."
}

$Npm = $null
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npmCommand) {
  $Npm = $npmCommand.Source
} else {
  $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
  if ($npmCommand) {
    $Npm = $npmCommand.Source
  }
}

if (!$Npm) {
  throw "npm was not found in PATH."
}

Stop-PortProcess -Port $BackendPort
Stop-PortProcess -Port $FrontendPort

$backendOut = Join-Path $Logs "backend-server.log"
$backendErr = Join-Path $Logs "backend-server.err.log"
$frontendOut = Join-Path $Logs "front-server.log"
$frontendErr = Join-Path $Logs "front-server.err.log"

if ((Split-Path $Python -Leaf) -ieq "py.exe") {
  $BackendArgs = @($PythonLauncherVersion, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
} else {
  $BackendArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
}

Start-Process -FilePath $Python `
  -ArgumentList $BackendArgs `
  -WorkingDirectory $Backend `
  -WindowStyle Hidden `
  -RedirectStandardOutput $backendOut `
  -RedirectStandardError $backendErr

Start-Sleep -Seconds 3

Start-Process -FilePath $Npm `
  -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort") `
  -WorkingDirectory $Frontend `
  -WindowStyle Hidden `
  -RedirectStandardOutput $frontendOut `
  -RedirectStandardError $frontendErr

Start-Sleep -Seconds 3

Write-Host "Lobster Quant dev services started."
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Backend docs: http://127.0.0.1:$BackendPort/docs"
Write-Host "Logs: $Logs"
