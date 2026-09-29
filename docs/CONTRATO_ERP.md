# Contrato fasa-erp-web → fasa-print-agent

El ERP **no imprime**: inserta una fila en `print_jobs` (ver
`migrations/001_create_print_jobs.sql`). El agente (SERVERFASA) hace
polling, genera el PDF si hace falta, resuelve la impresora e imprime.

## INSERT mínimo (REMITO_CTACTE con payload)

```sql
INSERT INTO print_jobs (
  estacion, tipo_impresion,
  documento_tipo, documento_id,
  copias, payload_json, solicitado_por
) VALUES (
  'VENTAS-07', 'REMITO_CTACTE',
  'REMITO', '956',
  1, :payload_json, :usuario
);
```

- `estacion`: puesto que originó el documento (`PC-OSCAR`, `VENTAS-07`,
  `CAJA-04`, …). **Nunca** `SERVERFASA`. Ver SPEC §8 (identidad
  `ESTACION_FASA` persistente en el ERP).
- `tipo_impresion`: `REMITO_CTACTE` (debe existir en
  `impresora_maquina` para esa estación).
- `documento_tipo` / `documento_id`: `REMITO` + id del remito (trazabilidad;
  índice único lógico para idempotencia en el ERP).
- `copias`: 1..5 (el agente rechaza fuera de rango: `COPIAS_INVALIDAS`).
- `payload_json`: objeto `REMITO_CTACTE` según
  `schemas/remito_ctacte.schema.json`. Ejemplo completo:
  `fixtures/remito_ctacte_ejemplo.json`.
- `archivo_path`: alternativa legada (PDF ya generado en ruta visible
  desde SERVERFASA). Si viene, tiene **prioridad** sobre el payload.

## Reglas del payload REMITO_CTACTE

- Todos los campos son strings (cantidades como texto: `"10,00"`).
- `cliente_codigo` se dibuja entre corchetes tras el nombre.
- `cliente_localidad`: el ERP la resuelve con join a su tabla
  `localidad`; el agente solo dibuja el string (más `cliente_cp`
  como `"CP - LOCALIDAD"` si ambos vienen).
- Campos vacíos/ausentes no se imprimen (sin error).
- **Límite: 12 ítems por remito** (zona central 58..113 mm, pitch 5 mm,
  última fila libre de observaciones). Más de 12 → el agente rechaza con
  `PAYLOAD_INVALIDO` y **no imprime nada**: nunca trunca en silencio.
  El ERP debe limitar a 12 ítems por remito antes de insertar el job.

## Lo que devuelve el agente (leer para la UI)

Estados en `print_jobs.estado`: `PENDIENTE → TOMADO → ENVIADO_SPOOLER →
IMPRESO`, o `ERROR` (con `error_code`/`error_message`), o reencolado a
`PENDIENTE` si quedan intentos.

Códigos que la UI del ERP debería contemplar:

| `error_code` | Significado | Acción sugerida |
|---|---|---|
| `PRINTER_MAPPING_NOT_FOUND` | Sin fila en `impresora_maquina` | Alta en configuración, reintentar |
| `PRINTER_NOT_AVAILABLE` | Impresora no visible desde SERVERFASA | Soporte, reintentar |
| `PAYLOAD_INVALIDO` | JSON malformado/incompleto | Bug en ERP, no reintentar a ciegas |
| `DOCUMENTO_FALTANTE` | Sin `archivo_path` ni `payload_json` | Bug en ERP |
| `COPIAS_INVALIDAS` / `TIPO_NO_PERMITIDO` | Validación | Bug en ERP |
| `SPOOLER_REJECTED` / `SPOOLER_ERROR` | Windows rechazó/falló | Reintentar, soporte |

`ENVIADO_SPOOLER` = Windows aceptó el trabajo (con `impresora_resuelta`
informada). No afirma papel en mano: la UI debe decir "Enviado a
impresión", nunca "Impreso" como hecho físico.

## Reimpresión

Siempre **nuevo INSERT** (nunca reciclar la fila anterior): queda
auditoría de fecha/usuario/estación/impresora/resultado.

## Probar el contrato sin ERP

```powershell
# 1) Generar el PDF que el agente generaría con ese payload:
python -m fasa_print_agent.main --save-remito-pdf C:\Temp\p.pdf --remito-json fixtures\remito_ctacte_ejemplo.json
# 2) Imprimirlo como lo haría el worker:
python -m fasa_print_agent.main --print-remito-pdf C:\Temp\p.pdf --printer "L395 Series(Network)"
# 3) Ver el historial en el panel:
python -m fasa_print_agent.main --panel
```
