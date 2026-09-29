# FASA Print Agent

Servicio de impresión centralizado para **Ferretería Avenida S.A. (FASA)**.

Corre en `SERVERFASA` (Windows Server 2019), hace polling a la tabla
`print_jobs` en MySQL, resuelve la impresora usando la configuración
histórica (`impresora_maquina` + `impresoras`) y envía el documento al
spooler de Windows **sin intervención del operador**.

Espec completa: `SPEC.md` (copia de `FASA_PRINT_AGENT_SPEC.md`).

## Arquitectura

```text
PC OPERADOR (navegador) → FASA ERP WEB → MySQL / print_jobs
    → FASA PRINT AGENT (SERVERFASA) → impresora física
```

- La **estación** (`VENTAS-07`, `CAJA-04`, …) es el puesto que originó
  el documento, nunca `SERVERFASA`.
- MVP: solo `REMITO_CTACTE` / documento `REMITO` (PDF A5).

## Requisitos

- Python 3.10+ (produción: Windows Server 2019)
- MySQL accesible (misma base del ERP)
- Impresoras instaladas en SERVERFASA con nombres estables

## Instalación rápida (desarrollo)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# editar .env con credenciales de desarrollo
python -m fasa_print_agent.main --health-check
python -m fasa_print_agent.main --list-printers
python -m fasa_print_agent.main --run-once
# loop continuo (consola):
python -m fasa_print_agent.main
```

## Uso

```text
fasa-print-agent.exe --health-check
fasa-print-agent.exe --list-printers
fasa-print-agent.exe --test-printer "Remito Cuenta Corriente"
fasa-print-agent.exe --run-once
```

Spike REMITO_CTACTE (A5, papel preimpreso — ver `docs/REMITO_SPIKE.md`):

```text
fasa-print-agent.exe --list-printers
fasa-print-agent.exe --save-remito-pdf C:\Temp\remito-test.pdf --remito-json fixtures\remito_ctacte_ejemplo.json
fasa-print-agent.exe --print-remito-pdf C:\Temp\remito-test.pdf --printer "Nombre impresora"
fasa-print-agent.exe --print-remito-test --printer "Nombre impresora" --out C:\Temp\remito-test.pdf
fasa-print-agent.exe --print-remito-test --printer "Nombre impresora" --offset-x 1.5 --offset-y -0.5
```

Panel de escritorio (ver trabajos enviados):

```text
fasa-print-agent.exe --panel
```

Lee el historial de `HISTORY_FILE` (defecto `<LOG_DIR>/print-history.jsonl`,
`off` lo desactiva), lista impresoras y permite disparar un remito test.

## Estructura

```text
src/fasa_print_agent/  → config, database, queue, printer_resolver,
                         windows_print, worker, diagnostics, logging_config, main
migrations/            → DDL de print_jobs
scripts/               → install_service.ps1, uninstall_service.ps1, test_environment.ps1
docs/                  → INSTALL_SERVERFASA.md, TROUBLESHOOTING.md
tests/                 → unitarios (resolver, queue, worker, config)
```

## Producción

Ver `docs/INSTALL_SERVERFASA.md`:

1. Instalar impresora en SERVERFASA y probar impresión manual.
2. Crear `C:\ProgramData\FASA Print Agent\agent.env`.
3. Ejecutar en consola y validar un `REMITO_CTACTE`.
4. Instalar como servicio (`scripts/install_service.ps1`).

## Seguridad

- No hardcodear credenciales; usar `agent.env` con ACL solo para
  Administradores + cuenta del servicio.
- El agente nunca ejecuta comandos arbitrarios del navegador; los
  destinos salen de `impresora_maquina`/`impresoras` y de allowlists.
