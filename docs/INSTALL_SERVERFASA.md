# Instalación en SERVERFASA

## 1. Pre-requisitos

- Windows Server 2019 con acceso a MySQL del ERP.
- Python 3.10+ instalado (marcar "Add to PATH").
- repo clonado en `C:\FASA\fasa-print-agent`.
- Impresora de prueba instalada con nombre estable (ej. `Remito Cuenta Corriente`).
- Impresión manual de prueba OK desde Windows (PDF A5).

## 2. Primera prueba real (SPEC §30)

```text
SERVERFASA + 1 impresora + REMITO_CTACTE + 1 Remito de prueba
```

1. `Copy-Item .env.example agent.env` → completar `DB_*`, `AGENT_NAME=SERVERFASA`.
2. Copiar a `C:\ProgramData\FASA Print Agent\agent.env` y restringir ACL:
   solo Administradores + cuenta del servicio.
3. Consola:
   ```powershell
   python -m fasa_print_agent.main --health-check
   python -m fasa_print_agent.main --list-printers
   ```
4. Insertar trabajo de prueba (con PDF A5 real en `archivo_path`):
   ```sql
   INSERT INTO print_jobs (estacion, tipo_impresion, documento_tipo,
     documento_id, copias, archivo_path, solicitado_por)
   VALUES ('VENTAS-07','REMITO_CTACTE','REMITO','TEST-001',1,
     'C:\\Temp\\remito-test.pdf','admin');
   ```
5. `python -m fasa_print_agent.main --run-once` → verificar papel + estado `IMPRESO` + logs.
6. Forzar error (detener impresora o estación inexistente) → `ERROR` con
   `PRINTER_MAPPING_NOT_FOUND` / `PRINTER_NOT_AVAILABLE`.
7. Reintentar: `UPDATE print_jobs SET estado='PENDIENTE' WHERE id=...`.

## 3. Servicio

```powershell
# como Administrador
.\scripts\install_service.ps1 -RepoDir C:\FASA\fasa-print-agent
```

Validar inicio automático tras reinicio y que la **cuenta del servicio**
ve las impresoras (una impresora visible para un usuario interactivo
puede no estarlo para `LocalSystem`; usar cuenta de servicio dedicada
si hay UNC/recursos autenticados — SPEC §23).

## 4. UNC / red

Para `\\EQUIPO\Impresora`: comprobar acceso desde la cuenta del servicio,
no solo desde tu sesión. Si falla, cambiar cuenta del servicio.
