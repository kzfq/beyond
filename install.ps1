# Beyond one-line installer (Windows PowerShell).
#   irm https://raw.githubusercontent.com/kzfq/beyond/main/install.ps1 | iex
# Installs git + python via winget if missing, clones Beyond, writes the config,
# installs the Python deps, and starts the agent (prints your link + password).
$ErrorActionPreference = "Stop"

$Repo      = "https://github.com/kzfq/beyond"
$EnrollKey = "zySlnMP0DRHwAz6Ax0Y2doZ6bTaDB_HNRF0N1PT_AK0"
$Dir       = Join-Path $HOME "beyond"

function Say($m) { Write-Host "[beyond] $m" -ForegroundColor Magenta }

function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path","User")
}

function Ensure($cmd, $id) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Say "Installing $cmd via winget…"
    winget install -e --id $id --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
  }
}

Ensure git    "Git.Git"
Ensure python "Python.Python.3.12"
Refresh-Path

if (Test-Path (Join-Path $Dir ".git")) {
  Say "Updating existing install…"; git -C $Dir pull --ff-only
} else {
  Say "Cloning Beyond…"; git clone $Repo $Dir
}
Set-Location $Dir

$cfg = "backend\agent_config.json"
if (-not (Test-Path $cfg)) {
  Say "Writing config…"
  @"
{
  "relay_base": "https://agent.selfbot.fyi",
  "viewer_base": "https://selfbot.fyi",
  "enroll_key": "$EnrollKey",
  "slug": "",
  "agent_secret": "",
  "viewer_password": ""
}
"@ | Set-Content -Encoding UTF8 $cfg
}

Say "Installing Python dependencies…"
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt

Say "Starting Beyond — your link + password appear below. Keep this window open."
python backend\beyond_agent.py
