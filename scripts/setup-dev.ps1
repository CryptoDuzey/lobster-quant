param(
  [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "front"
$VenvPython = Join-Path $Root ".venv-rqsdk\Scripts\python.exe"

if (!(Test-Path $VenvPython)) {
  Write-Host "Creating Python virtual environment..."
  & $PythonCommand -m venv (Join-Path $Root ".venv-rqsdk")
}

Write-Host "Installing backend dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Backend "requirements.txt")

if (!(Test-Path (Join-Path $Backend ".env")) -and (Test-Path (Join-Path $Backend ".env.example"))) {
  Copy-Item (Join-Path $Backend ".env.example") (Join-Path $Backend ".env")
  Write-Host "Created backend/.env from example. Fill DEEPSEEK_API_KEY if you need AI chat."
}

if (!(Test-Path (Join-Path $Frontend ".env")) -and (Test-Path (Join-Path $Frontend ".env.example"))) {
  Copy-Item (Join-Path $Frontend ".env.example") (Join-Path $Frontend ".env")
}

Write-Host "Installing frontend dependencies..."
Push-Location $Frontend
npm install
Pop-Location

Write-Host "Setup complete. Run .\scripts\start-dev.ps1 to start Lobster Quant."
