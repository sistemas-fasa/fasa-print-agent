# Diagnóstico del entorno (SPEC §21, §30). Ejecutar en SERVERFASA.
param([string]$EnvFile = "C:\ProgramData\FASA Print Agent\agent.env")
$ErrorActionPreference = "Continue"
Write-Host "== FASA Print Agent: test_environment ==" -ForegroundColor Cyan
Write-Host "Python:"; python --version
Write-Host "`n--health-check:"; python -m fasa_print_agent.main --env-file $EnvFile --health-check
Write-Host "`n--list-printers:"; python -m fasa_print_agent.main --env-file $EnvFile --list-printers
Write-Host "`nSpooler (Get-Printer):"
Get-Printer | Select-Object Name, DriverName, PortName, PrinterStatus | Format-Table -AutoSize
Write-Host "`nVariables de entorno clave (sin secretos):"
Get-ChildItem Env:AGENT_NAME, Env:POLL_SECONDS -ErrorAction SilentlyContinue | Format-Table -AutoSize
