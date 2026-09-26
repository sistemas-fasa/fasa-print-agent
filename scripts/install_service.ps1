# Instalación del servicio en SERVERFASA (Windows Server 2019).
# Requisitos: Python 3.10+, repo clonado, impresoras instaladas.
# Ejecutar como Administrador.
param(
  [string]$RepoDir = "C:\FASA\fasa-print-agent",
  [string]$PythonExe = "python",
  [string]$ServiceAccount = "",
  [string]$NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
)
$ErrorActionPreference = "Stop"

$agentDir = "C:\ProgramData\FASA Print Agent"
$envFile = Join-Path $agentDir "agent.env"
$logDir = Join-Path $agentDir "logs"

Write-Host "== FASA Print Agent: instalacion ==" -ForegroundColor Cyan
Write-Host "Repo: $RepoDir"

if (-not (Test-Path -LiteralPath $RepoDir)) { throw "No existe RepoDir: $RepoDir" }
New-Item -ItemType Directory -Path $agentDir -Force | Out-Null
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Push-Location $RepoDir
try {
  & $PythonExe -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install --upgrade pip
  pip install .
  # Validación previa (no requiere impresora física para health-check de DB)
  python -m fasa_print_agent.main --health-check
} finally {
  Pop-Location
}

if (-not (Test-Path -LiteralPath $envFile)) {
  Write-Warning "No existe $envFile — crealo a partir de .env.example antes de iniciar el servicio."
}

# Servicio vía NSSM (recomendado) — alternativa: sc.exe / win32service.
$nssm = Join-Path $agentDir "nssm.exe"
if (-not (Test-Path -LiteralPath $nssm)) {
  Write-Host "Descargando NSSM..."
  $zip = Join-Path $env:TEMP "nssm.zip"
  Invoke-WebRequest -Uri $NssmUrl -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath (Join-Path $env:TEMP "nssm") -Force
  Copy-Item (Join-Path $env:TEMP "nssm\nssm-2.24\win64\nssm.exe") $nssm -Force
}
$py = Join-Path $RepoDir ".venv\Scripts\python.exe"
& $nssm install "FASA Print Agent" $py "-m" "fasa_print_agent.main"
& $nssm set "FASA Print Agent" AppDirectory $RepoDir
& $nssm set "FASA Print Agent" Start SERVICE_AUTO_START
& $nssm set "FASA Print Agent" AppStdout (Join-Path $logDir "service-stdout.log")
& $nssm set "FASA Print Agent" AppStderr (Join-Path $logDir "service-stderr.log")
if ($ServiceAccount -ne "") {
  Write-Host "Cuenta de servicio solicitada: $ServiceAccount (configurar password con nssm edit)"
}
Write-Host "OK. Revisar con: nssm status 'FASA Print Agent'" -ForegroundColor Green
Write-Host "IMPORTANTE: validar que la cuenta del servicio ve las impresoras (--list-printers)." -ForegroundColor Yellow
