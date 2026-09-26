# Desinstalación del servicio. Ejecutar como Administrador.
param([string]$AgentDir = "C:\ProgramData\FASA Print Agent")
$ErrorActionPreference = "Stop"
$nssm = Join-Path $AgentDir "nssm.exe"
if (Test-Path -LiteralPath $nssm) {
  & $nssm stop "FASA Print Agent"
  & $nssm remove "FASA Print Agent" confirm
  Write-Host "Servicio eliminado." -ForegroundColor Green
} else {
  sc.exe delete "FASA Print Agent"
}
