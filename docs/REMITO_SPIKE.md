# Spike REMITO_CTACTE — procedimiento en SERVERFASA

Objetivo: demostrar que SERVERFASA imprime un remito A5 (210 x 148 mm,
solo datos variables sobre papel preimpreso) en una impresora Windows
real, sin navegador, sin Adobe, sin diálogos.

## 0. Preparar

```powershell
cd C:\FASA\fasa-print-agent
git pull
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Papel: remito preimpreso A5 cargado en la impresora de prueba.
Bandeja/driver: tamaño **A5 apaisado**. El agente fija A5 apaisado vía
DEVMODE en memoria y avisa en logs (`PRINTER_CAPS ... no es A5`) si el
driver informa otro tamaño.

## 1. Listar impresoras (cuenta del agente)

```powershell
python -m fasa_print_agent.main --list-printers
```

Anotar el nombre EXACTO, ej. `L395 Series(Network)`.
Si la impresora no aparece: es problema de cuenta del servicio
(SPEC §23) — validar antes de seguir.

## 2. Generar el remito de prueba (sin imprimir)

```powershell
python -m fasa_print_agent.main --save-remito-pdf C:\Temp\remito-test.pdf --remito-json fixtures\remito_ctacte_ejemplo.json
```

Respuesta esperada: `GENERADO_OK: C:\Temp\remito-test.pdf ...`.

## 3. Inspeccionar el PDF

Abrir `C:\Temp\remito-test.pdf` y verificar: página de 210 x 148 mm,
solo datos variables (número arriba-derecha, cliente, ítem, pie de
transportista). Sin logo ni formulario: eso ya está preimpreso.

## 4. Imprimir ese mismo remito

```powershell
python -m fasa_print_agent.main --print-remito-pdf C:\Temp\remito-test.pdf --printer "NOMBRE EXACTO"
```

Respuesta esperada: `SPOOL_OK: ... windows_job_id=N` seguido de
`ENVIADO_SPOOLER: Windows aceptó el trabajo. Verificar papel físico.`

Atajo (genera + imprime en un paso):

```powershell
python -m fasa_print_agent.main --print-remito-test --printer "NOMBRE EXACTO" --out C:\Temp\remito-test.pdf
```

Solo generar (equivalente al paso 2):

```powershell
python -m fasa_print_agent.main --print-remito-test --no-print --out C:\Temp\remito-test.pdf
```

## 5. Calibrar (±1/2 mm con regla sobre el papel impreso)

Desvío global (no toca código):

```powershell
python -m fasa_print_agent.main --print-remito-test --printer "NOMBRE" --out C:\Temp\remito-test.pdf --offset-x 1.5 --offset-y -0.5
```

Posiciones individuales: exportar, editar y reusar el layout:

```powershell
python -m fasa_print_agent.main --write-remito-layout C:\Temp\remito-layout.json
# editar x_mm/y_mm con un editor, luego:
python -m fasa_print_agent.main --save-remito-pdf C:\Temp\remito-test.pdf --layout-json C:\Temp\remito-layout.json
```

Origen de coordenadas: esquina superior izquierda, X→derecha,
Y→abajo, todo en mm (`src/fasa_print_agent/remito_layout.py`).
Posiciones definitivas: volcar el `remito-layout.json` calibrado al
issue de calibración para fijarlo como default.

## 6. Logs y diagnóstico

- Consola: líneas `GENERADO_OK` / `SPOOL_OK` / `SPOOL_ERROR code=...`, más
  `PRINTER_CAPS <impresora> papel=...` (verifica A5 210x148 del driver).
- Archivo: `C:\ProgramData\FASA Print Agent\logs\fasa-print-agent.log`
  (rotativo, ver `LOG_DIR` en `.env`).
- Códigos de error: `FILE_NOT_FOUND`, `PRINTER_NOT_AVAILABLE`,
  `SPOOLER_REJECTED`, `SPOOLER_ERROR`, `RENDER_ERROR`, `PDF_INVALID`,
  `NO_PRINT_BACKEND` (esto último = no estás en Windows).

## 7. Semántica (importante)

- `GENERADO_OK` = PDF creado, nada enviado.
- `SPOOL_OK` / `windows_job_id=N` = el spooler de Windows aceptó el
  trabajo. NO afirma que el papel salió: Windows no lo confirma de
  forma fiable. Verificar físicamente.
- Si el papel sale en blanco o desplazado: es calibración
  (paso 5), no reintentar como error de spooler.

## Bitácora de calibración L395 (papel preimpreso real)

- Job 1-2 (apaisado + tamaño usuario): datos **rotados 90°**. Causa: la
  L395 no trae A5 y su driver rota los jobs apaisados con tamaño custom.
- Job 5-7 (`--dc-mode user-portrait`, luego default por quirk `L395`):
  datos **derechos**. Estrategia: vertical + USER 1480x2100 → DC 204x142
  sin rotación del driver.
- Job 7: `offset-y=3` (todo 3 mm abajo, primer ajuste pedido).
- Job 8: layout consolidado (offset plegado, fecha 16→31 tras confirmar
  que "120mm" era typo de 12mm). Todo validado salvo confirmación final.
- Pendiente: verificar por zona con regla (número, cliente, ítems,
  transportista) y fijar posiciones finales en `remito_layout.py`.

## Decisiones técnicas del spike (verificadas 29/09/2026)

- Sin `ShellExecute("print")`: dependía del visor PDF asociado y sus
  diálogos; inaceptable desde un servicio.
- Sin SumatraPDF obligatorio: quedó solo como fallback explícito si
  `SUMATRA_PDF_PATH` está configurado.
- Mecanismo: PyMuPDF rasteriza a BMP 24-bit (escritor propio, sin
  Pillow) → GDI `StretchBlt` sobre DC con papel A5 apaisado.
- pywin32 312 no acepta DEVMODE en `CreatePrinterDC` (1 solo argumento),
  así que el DC se crea por-job vía ctypes: `winspool.DocumentPropertiesW`
  (DEVMODE del driver con su parte privada) + `gdi32.CreateDCW` con el
  DEVMODE parcheado en memoria. **Nunca `SetPrinter`: nada persiste.**
- Cadena por impresora (con verificación de tamaño real del DC):
  1. A5-enum (`DMPAPER_A5`); 2. tamaño usuario 210x148 mm (los Epson
  como L395 ignoran el enum y solo aceptan este); 3. defaults con aviso.
  RICOH acepta A5-enum; L395 requirió tamaño usuario (verificado:
  DC 204x142 = área imprimible A5).
- Rect destino 1:1 en mm sobre la hoja física completa, compensando
  márgenes no imprimibles (`PHYSICALOFFSETX/Y`); GDI recorta lo que caiga
  fuera. El layout deja ≥9 mm de margen, dentro de lo imprimible.
- `windows_job_id`: pywin32 `StartDoc` retorna None; el id real se
  recupera best-effort con `EnumJobs` tras `EndDoc`.
- Salida de consola compatible cp1252 (sin flechas unicode).
