# Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `PRINTER_MAPPING_NOT_FOUND` | Falta fila en `impresora_maquina` para `estacion+tipo` | Revisar mapping VFP; no se elige impresora arbitraria |
| `PRINTER_NOT_AVAILABLE` | Cuenta del servicio no ve la impresora | `--list-printers` desde esa cuenta; revisar §23 |
| `MySQL FAIL` | Credenciales/red | Revisar `agent.env`, firewall, usuario `fasa_print` |
| Job queda `TOMADO` sin avanzar | Agente muerto a mitad de impresión | Reiniciar agente; el job se reintenta manualmente a `PENDIENTE` |
| Duplicados | Doble click / reintento HTTP | Reimpresión crea nuevo job (auditable); reclamo atómico evita doble spool |
| `NO_PRINT_BACKEND` | Sin SumatraPDF fuera de Windows | Instalar SumatraPDF o correr en SERVERFASA |
| Logs gigantes | Rotación | `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` en `agent.env` |

Logs: `C:\ProgramData\FASA Print Agent\logs\fasa-print-agent.log`
(fallback consola si el servicio no puede escribir).

Comandos:

```powershell
python -m fasa_print_agent.main --health-check
python -m fasa_print_agent.main --list-printers
python -m fasa_print_agent.main --test-printer "Remito Cuenta Corriente"
python -m fasa_print_agent.main --run-once
```
