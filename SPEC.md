# FASA Print Agent --- Especificación funcional y técnica

**Proyecto propuesto:** `fasa-print-agent`\
**Cliente:** Ferretería Avenida S.A. (FASA)\
**Plataforma objetivo del agente:** Windows Server 2019 (`SERVERFASA`)\
**Integración inicial:** `oscarvogel/fasa-erp-web`\
**Estado:** Especificación inicial / MVP\
**Fecha:** 2026-09-26

------------------------------------------------------------------------

## 1. Objetivo

Implementar un servicio de impresión específico para FASA que permita
que `fasa-erp-web` envíe documentos directamente a las impresoras
configuradas para cada puesto y tipo de documento, sin depender del
cuadro de impresión del navegador y sin instalar todas las impresoras en
cada computadora cliente.

La primera implementación debe aprovechar la configuración histórica
existente en FASA (`impresora_maquina` e `impresoras`) para reducir al
mínimo la migración operativa.

Este proyecto **no pretende ser Vogel Print Services** ni una plataforma
genérica multiempresa. Es una solución específica para FASA y puede
depender de sus tablas, convenciones y red actual.

------------------------------------------------------------------------

## 2. Problema actual

El ERP web puede generar un documento imprimible, pero el navegador no
debe ser responsable de seleccionar silenciosamente una impresora
Windows específica.

El flujo actual con `window.print()`:

1.  abre el diálogo de impresión del navegador;
2.  obliga al operador a seleccionar/configurar impresora;
3.  depende de las impresoras instaladas en cada puesto;
4.  permite errores humanos;
5.  no reproduce la operatoria automática del sistema VFP existente.

FASA ya dispone de configuración que relaciona:

-   máquina/puesto;
-   tipo lógico de impresión;
-   impresora correspondiente.

El objetivo es conservar ese comportamiento en el ERP web.

------------------------------------------------------------------------

## 3. Principio de arquitectura

Las PCs de los operadores utilizarán solamente el navegador.

Las impresoras se instalarán/configurarán principalmente en
`SERVERFASA`, que ejecutará el agente de impresión.

``` text
PC OPERADOR
   │
   │ navegador
   ▼
FASA ERP WEB
   │
   │ crea trabajo de impresión
   ▼
MYSQL / PRINT_JOBS
   │
   │ polling
   ▼
FASA PRINT AGENT
SERVERFASA - Windows Server 2019
   │
   ├── impresora A
   ├── impresora B
   ├── impresora C
   └── impresoras compartidas / red / IP
```

La máquina que origina el documento y la máquina que físicamente ejecuta
la impresión son conceptos diferentes.

Ejemplo:

``` text
Origen: VENTAS-07
Tipo:   REMITO_REP_99

impresora_maquina
VENTAS-07 + REMITO_REP_99
        ↓
Pedidos_Local_Comercial
        ↓
SERVERFASA imprime físicamente
```

------------------------------------------------------------------------

## 4. Alcance del MVP

El MVP debe validar el circuito completo utilizando inicialmente:

**Tipo de documento:** Remito\
**Tipo lógico inicial:** `REMITO_CTACTE`

El MVP deberá:

1.  identificar el puesto que solicita la impresión;
2.  recibir/crear un trabajo de impresión;
3.  persistirlo;
4.  resolver la impresora mediante la configuración actual de FASA;
5.  permitir que `SERVERFASA` tome el trabajo;
6.  imprimir sin intervención del operador;
7.  registrar resultado;
8.  registrar errores y reintentos;
9.  permitir reimpresión;
10. mantener la impresión manual del navegador como contingencia durante
    la transición.

No se incorporarán inicialmente todos los tipos históricos de impresión.

Una vez validado `REMITO_CTACTE`, se incorporarán progresivamente:

-   remitos de reparto;
-   presupuestos;
-   recibos;
-   pedidos;
-   facturas;
-   otros tipos actualmente utilizados por VFP.

------------------------------------------------------------------------

## 5. Repositorios

### `oscarvogel/fasa-erp-web`

Responsabilidades:

-   interfaz del operador;
-   generación del documento;
-   identificación del documento;
-   solicitud de impresión;
-   selección del tipo lógico de impresión;
-   visualización del estado;
-   reimpresión;
-   fallback de impresión manual.

### `oscarvogel/fasa-print-agent`

Responsabilidades:

-   procesamiento de la cola;
-   resolución de impresoras FASA;
-   interacción con Windows;
-   envío al spooler;
-   reintentos;
-   logs;
-   diagnóstico;
-   actualización del estado de los trabajos.

El agente no debe contener lógica comercial de Remitos.

------------------------------------------------------------------------

## 6. SERVERFASA

Servidor previsto:

``` text
Nombre: SERVERFASA
Sistema operativo: Windows Server 2019
Función nueva: servidor central de impresión para FASA
```

`SERVERFASA` deberá tener instaladas o accesibles las impresoras
necesarias.

Siempre que sea posible:

-   instalar las impresoras de red directamente en SERVERFASA;
-   evitar depender de una PC de usuario;
-   usar nombres de impresora estables;
-   validar permisos de la cuenta que ejecuta el servicio.

Para impresoras accesibles mediante UNC, por ejemplo:

``` text
\\DAMIAN_2\HP LaserJet 1160
```

deberá comprobarse que la cuenta del servicio pueda acceder al recurso.

------------------------------------------------------------------------

## 7. Configuración histórica de FASA

### 7.1 `impresora_maquina`

Esta tabla seguirá siendo inicialmente la fuente para determinar qué
impresora corresponde a una combinación de:

``` text
MAQUINA + TIPO_IMPRESION
```

Ejemplo conceptual:

``` text
VENTAS-07 + REMITO_REP_99
    → Pedidos_Local_Comercial
```

No duplicar esta configuración en el nuevo agente durante el MVP.

### 7.2 `impresoras`

La tabla existente contiene información adicional del destino
lógico/físico.

El agente deberá estudiar y soportar los valores utilizados actualmente,
que pueden representar:

-   nombre de impresora Windows;
-   impresora compartida;
-   UNC;
-   dirección IP;
-   alias histórico.

No asumir que todos los registros tienen exactamente el mismo formato.

------------------------------------------------------------------------

## 8. Identificación de la estación

Este punto es obligatorio.

El navegador no puede considerarse una fuente confiable del
`COMPUTERNAME` de Windows.

Sin embargo, la configuración histórica depende de valores como:

``` text
PC-OSCAR
VENTAS-07
CAJA-04
EDUARDO-PC
DEPOSITOCEMENTO
```

Por lo tanto, `fasa-erp-web` deberá disponer de una identidad de
estación persistente.

### Propuesta MVP

Agregar un concepto:

``` text
ESTACION_FASA
```

La primera vez que un navegador/puesto use impresión automática, se
asocia con una estación conocida.

Ejemplo:

``` text
Navegador de la PC de Oscar
        ↓
ESTACION_FASA = PC-OSCAR
```

La asociación debe persistir localmente y/o en backend mediante un
identificador de estación.

No pedir la estación antes de cada impresión.

Debe existir una opción administrativa para cambiarla.

### Importante

La estación representa **el puesto que originó la impresión**, no
`SERVERFASA`.

Nunca resolver impresoras usando `SERVERFASA` como estación cuando el
trabajo fue solicitado por `VENTAS-07`, `CAJA-04`, etc.

------------------------------------------------------------------------

## 9. Cola de impresión

Crear una tabla específica para los trabajos.

Nombre sugerido:

``` sql
print_jobs
```

Modelo inicial recomendado:

``` sql
CREATE TABLE print_jobs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    empresa_id BIGINT NULL,

    estacion VARCHAR(100) NOT NULL,
    tipo_impresion VARCHAR(100) NOT NULL,

    documento_tipo VARCHAR(50) NOT NULL,
    documento_id VARCHAR(100) NOT NULL,

    impresora_resuelta VARCHAR(255) NULL,

    copias INT NOT NULL DEFAULT 1,

    payload_json JSON NULL,
    archivo_path VARCHAR(500) NULL,

    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',

    intentos INT NOT NULL DEFAULT 0,
    max_intentos INT NOT NULL DEFAULT 3,

    solicitado_por VARCHAR(150) NULL,

    created_at DATETIME NOT NULL,
    claimed_at DATETIME NULL,
    spooled_at DATETIME NULL,
    printed_at DATETIME NULL,
    failed_at DATETIME NULL,

    agent_name VARCHAR(100) NULL,
    error_code VARCHAR(100) NULL,
    error_message TEXT NULL,

    PRIMARY KEY (id),

    INDEX idx_print_jobs_estado (estado),
    INDEX idx_print_jobs_estacion (estacion),
    INDEX idx_print_jobs_documento (documento_tipo, documento_id),
    INDEX idx_print_jobs_created_at (created_at)
);
```

El esquema definitivo debe adaptarse al esquema/migraciones reales de
FASA.

------------------------------------------------------------------------

## 10. Estados

No considerar que un documento está impreso solamente porque fue creado
en la cola.

Estados mínimos:

``` text
PENDIENTE
TOMADO
ENVIADO_SPOOLER
IMPRESO
ERROR
CANCELADO
```

Flujo normal:

``` text
PENDIENTE
   ↓
TOMADO
   ↓
ENVIADO_SPOOLER
   ↓
IMPRESO
```

Flujo de error:

``` text
PENDIENTE
   ↓
TOMADO
   ↓
ERROR
```

Dependiendo del error:

``` text
ERROR
  ↓
PENDIENTE
```

para reintento.

### Semántica

`ENVIADO_SPOOLER` significa que Windows aceptó el trabajo.

No afirmar más precisión de la que permita Windows/driver. Si no existe
confirmación fiable de que el papel salió físicamente, `IMPRESO` debe
representar el nivel de confirmación realmente disponible y quedar
documentado.

------------------------------------------------------------------------

## 11. Evitar impresiones duplicadas

La cola debe ser segura frente a:

-   reinicio del agente;
-   pérdida temporal de MySQL;
-   dos ciclos de polling simultáneos;
-   timeout después de enviar al spooler;
-   doble click del operador;
-   reintentos HTTP.

El agente debe reclamar el trabajo atómicamente antes de imprimir.

Nunca:

``` text
SELECT pendiente
→ imprimir
→ UPDATE
```

sin mecanismo de exclusión.

Debe implementarse locking/transición atómica adecuada para la versión
de MySQL utilizada.

También debe existir un identificador/idempotency key para solicitudes
provenientes del ERP cuando corresponda.

------------------------------------------------------------------------

## 12. Documento imprimible

Para el MVP de Remitos, el documento debe ser reproducible
independientemente del navegador.

No utilizar una captura del DOM del navegador como formato principal del
agente.

Opciones aceptables a evaluar durante implementación:

1.  PDF generado por backend;
2.  PDF generado por un servicio de render;
3.  formato específico renderizado por el agente.

Para el MVP se priorizará **PDF listo para imprimir**, porque desacopla
el diseño del documento de la impresora y del navegador.

El PDF de Remito debe respetar el formato físico requerido, inicialmente
A5 si ese es el formato operativo confirmado.

------------------------------------------------------------------------

## 13. Flujo de impresión de Remito

### Emisión

``` text
Usuario genera Remito
        ↓
Remito se persiste correctamente
        ↓
ERP determina estación
        ↓
ERP determina tipo lógico
        ↓
Genera documento imprimible
        ↓
Crea print_job
        ↓
UI muestra "Enviado a impresión"
        ↓
Agent toma trabajo
        ↓
Resuelve impresora
        ↓
Imprime
        ↓
Actualiza estado
```

La persistencia del Remito y la impresión son procesos diferentes.

Un fallo de impresora **no debe borrar ni invalidar el Remito emitido**.

------------------------------------------------------------------------

## 14. Reimpresión

La pantalla de búsqueda/reimpresión de Remitos de `fasa-erp-web` deberá
finalmente ofrecer:

``` text
Reimprimir
```

La reimpresión crea **un nuevo `print_job`**.

Nunca reutilizar destructivamente el trabajo anterior.

Debe quedar auditado:

-   documento;
-   fecha;
-   usuario;
-   estación;
-   impresora;
-   cantidad de copias;
-   resultado.

Esto permitirá saber cuántas veces fue enviado un Remito a impresión.

------------------------------------------------------------------------

## 15. Resolución de impresora

Flujo inicial:

``` text
estacion
+
tipo_impresion
        ↓
impresora_maquina
        ↓
impresora lógica
        ↓
impresoras
        ↓
destino utilizable por Windows
```

Si no existe configuración:

``` text
estado = ERROR
error_code = PRINTER_MAPPING_NOT_FOUND
```

No elegir una impresora arbitraria.

Si existe configuración pero SERVERFASA no encuentra la impresora:

``` text
estado = ERROR
error_code = PRINTER_NOT_AVAILABLE
```

------------------------------------------------------------------------

## 16. Fallback manual

Durante la implantación se mantendrá:

``` text
Vista previa / Imprimir manualmente
```

Esto permitirá operar si:

-   SERVERFASA está apagado;
-   agente detenido;
-   impresora fuera de línea;
-   configuración incompleta;
-   problema de red.

La impresión automática no debe eliminar inicialmente el mecanismo
manual existente.

------------------------------------------------------------------------

## 17. Agente Windows

Tecnología propuesta:

``` text
Python 3.x
```

El proceso debe poder ejecutarse:

1.  en consola durante desarrollo;
2.  como servicio Windows en producción.

Nombre sugerido del servicio:

``` text
FASA Print Agent
```

Nombre interno:

``` text
fasa-print-agent
```

El servicio debe iniciar automáticamente con Windows.

------------------------------------------------------------------------

## 18. Configuración del agente

No hardcodear credenciales.

Archivo sugerido:

``` text
C:\ProgramData\FASA Print Agent\agent.env
```

Ejemplo conceptual:

``` env
AGENT_NAME=SERVERFASA
POLL_SECONDS=2

DB_HOST=...
DB_PORT=3306
DB_NAME=...
DB_USER=...
DB_PASSWORD=...

LOG_LEVEL=INFO
```

Las credenciales definitivas deberán almacenarse de manera
razonablemente segura para el entorno Windows utilizado.

------------------------------------------------------------------------

## 19. Polling

Para FASA se priorizará polling sobre WebSockets.

Ejemplo:

``` text
cada 2 segundos
    ↓
buscar trabajos pendientes
    ↓
reclamar trabajo
    ↓
procesar
    ↓
actualizar resultado
```

Ventajas:

-   simple;
-   robusto;
-   fácil de diagnosticar;
-   no requiere conexiones persistentes;
-   tolera reinicios;
-   funciona bien con la escala de FASA.

El intervalo debe ser configurable.

------------------------------------------------------------------------

## 20. Logs

Los logs son obligatorios.

Ruta sugerida:

``` text
C:\ProgramData\FASA Print Agent\logs\
```

Registrar como mínimo:

``` text
timestamp
agent
job_id
estacion
tipo_impresion
documento
documento_id
impresora
acción
resultado
duración
error
```

Ejemplo:

``` text
2026-09-26 11:32:10
JOB=1528
ESTACION=VENTAS-07
TIPO=REMITO_CTACTE
DOC=REMITO/956
PRINTER=Remito Cuenta Corriente
RESULT=OK
```

Los logs no deben contener contraseñas ni secretos.

Implementar rotación para evitar crecimiento indefinido.

------------------------------------------------------------------------

## 21. Diagnóstico

El ejecutable debería soportar comandos de diagnóstico.

Ejemplos:

``` text
fasa-print-agent.exe --health-check
fasa-print-agent.exe --list-printers
fasa-print-agent.exe --test-printer "Remito Cuenta Corriente"
fasa-print-agent.exe --run-once
```

`--health-check` debe comprobar como mínimo:

-   configuración;
-   conexión MySQL;
-   acceso a tablas necesarias;
-   disponibilidad del spooler Windows;
-   identidad del agente.

`--list-printers` debe listar las impresoras que Windows realmente ve
desde la cuenta del agente.

Esto será fundamental para soporte remoto.

------------------------------------------------------------------------

## 22. Seguridad

El agente no debe aceptar desde el navegador comandos arbitrarios del
tipo:

``` text
ejecutar este comando
imprimir este path local
usar esta UNC arbitraria
```

Los destinos deben surgir de configuración confiable.

Validar:

-   tipos de impresión permitidos;
-   documentos permitidos;
-   rutas;
-   impresoras;
-   cantidad de copias.

No ejecutar shell construido con datos provenientes directamente del
usuario.

------------------------------------------------------------------------

## 23. Cuenta del servicio Windows

Debe decidirse qué usuario ejecutará `FASA Print Agent`.

Esto es importante porque una impresora visible para un usuario
interactivo puede no estar visible para `LocalSystem`.

Durante instalación se deberá validar:

``` text
cuenta del servicio
    ↓
ve impresoras
    ↓
tiene acceso a shares
    ↓
puede enviar trabajos
```

Si se utilizan impresoras UNC o recursos autenticados, probablemente
convenga una cuenta Windows específica de servicio con permisos
adecuados.

------------------------------------------------------------------------

## 24. Administración desde FASA ERP Web

No construir un frontend independiente para el MVP.

Más adelante `fasa-erp-web` podrá mostrar una sección:

``` text
Administración
└── Impresión
```

Con:

-   trabajos recientes;
-   pendientes;
-   errores;
-   reintentar;
-   cancelar;
-   estación;
-   impresora;
-   documento;
-   usuario;
-   fecha/hora;
-   diagnóstico del agente.

Pero esto no debe bloquear la primera prueba real.

------------------------------------------------------------------------

## 25. UI del operador

El operador no debería necesitar conocer la cola.

Flujo deseado:

``` text
Generar remito
```

Resultado normal:

``` text
✓ Remito generado
✓ Enviado a impresión
```

Si hay un problema:

``` text
Remito generado correctamente.
No pudo imprimirse automáticamente.

[Reintentar impresión]
[Imprimir manualmente]
```

Nunca mostrar un error de impresora como si hubiera fallado la creación
del Remito.

------------------------------------------------------------------------

## 26. Compatibilidad con VFP

Durante la transición pueden coexistir:

``` text
VFP
+
FASA ERP Web
+
FASA Print Agent
```

No modificar las tablas históricas de impresoras de forma incompatible
con VFP sin una necesidad comprobada.

La migración debe ser progresiva.

El objetivo inicial es que ambos sistemas puedan convivir.

------------------------------------------------------------------------

## 27. Fuera de alcance

No implementar en este proyecto:

-   multiempresa genérico;
-   administración SaaS;
-   discovery automático de redes;
-   soporte para clientes distintos de FASA;
-   API pública genérica;
-   Vogel Print Services;
-   reemplazo completo inmediato de la configuración histórica;
-   instalación de agente en cada PC;
-   administración avanzada de drivers;
-   impresión desde Internet directamente hacia IPs privadas.

Esos problemas pertenecen al futuro proyecto Vogel Print Services.

------------------------------------------------------------------------

## 28. Estructura sugerida del repo

``` text
fasa-print-agent/
├── src/
│   └── fasa_print_agent/
│       ├── __init__.py
│       ├── config.py
│       ├── main.py
│       ├── worker.py
│       ├── database.py
│       ├── queue.py
│       ├── printer_resolver.py
│       ├── windows_print.py
│       ├── diagnostics.py
│       └── logging_config.py
│
├── tests/
│   ├── test_queue.py
│   ├── test_printer_resolver.py
│   ├── test_worker.py
│   └── test_config.py
│
├── scripts/
│   ├── install_service.ps1
│   ├── uninstall_service.ps1
│   └── test_environment.ps1
│
├── migrations/
│   └── ...
│
├── docs/
│   ├── INSTALL_SERVERFASA.md
│   └── TROUBLESHOOTING.md
│
├── .env.example
├── pyproject.toml
├── README.md
└── SPEC.md
```

------------------------------------------------------------------------

## 29. Estrategia de pruebas

### Unitarias

Cubrir:

-   resolución estación/tipo;
-   mapping inexistente;
-   impresora inexistente;
-   transiciones de estado;
-   reintentos;
-   idempotencia;
-   límites de copias;
-   errores de DB.

### Integración

Probar contra MySQL de desarrollo con datos representativos de:

``` text
impresora_maquina
impresoras
print_jobs
```

### Windows

Pruebas obligatorias en SERVERFASA:

1.  listar impresoras;
2.  imprimir página de prueba;
3.  imprimir PDF A5;
4.  detener impresora y validar ERROR;
5.  reactivar y reintentar;
6.  reiniciar agente con trabajo pendiente;
7.  reiniciar SERVERFASA;
8.  validar inicio automático;
9.  validar impresora UNC;
10. validar impresora de red/IP.

------------------------------------------------------------------------

## 30. Primera prueba real

No comenzar intentando soportar todas las impresoras.

Primera prueba:

``` text
SERVERFASA
+
una impresora conocida
+
REMITO_CTACTE
+
un Remito de prueba
```

Secuencia:

``` text
1. Instalar/configurar impresora en SERVERFASA.
2. Confirmar impresión manual desde Windows Server.
3. Ejecutar agente en consola.
4. Insertar trabajo de prueba.
5. Resolver impresora usando tablas FASA.
6. Imprimir.
7. Verificar estado.
8. Verificar logs.
9. Forzar un error.
10. Verificar recuperación/reintento.
```

Recién después instalarlo como servicio.

------------------------------------------------------------------------

## 31. Criterios de aceptación del MVP

El MVP se considera validado cuando:

-   SERVERFASA puede ejecutar el agente;
-   el agente inicia sin intervención;
-   conecta a MySQL;
-   detecta un trabajo `REMITO_CTACTE`;
-   identifica correctamente la estación origen;
-   consulta la configuración histórica;
-   resuelve la impresora correcta;
-   imprime un Remito real con formato correcto;
-   no aparece el diálogo de impresión en la PC del operador;
-   la PC del operador no necesita tener esa impresora instalada;
-   queda trazabilidad del trabajo;
-   un error queda registrado;
-   el error puede reintentarse;
-   un reinicio del agente no provoca impresiones duplicadas;
-   puede reimprimirse un Remito creando un nuevo trabajo;
-   continúa disponible el fallback manual.

------------------------------------------------------------------------

## 32. Fases propuestas

### Fase 1 --- Investigación y spike Windows

-   confirmar esquema real de tablas;
-   listar impresoras desde SERVERFASA;
-   seleccionar librería/método de impresión;
-   imprimir PDF A5 de prueba.

### Fase 2 --- Cola

-   migración `print_jobs`;
-   repositorio MySQL;
-   locking;
-   estados;
-   reintentos;
-   logs.

### Fase 3 --- Resolución FASA

-   `impresora_maquina`;
-   `impresoras`;
-   errores de configuración;
-   tests con mappings reales.

### Fase 4 --- Servicio Windows

-   ejecutable;
-   configuración;
-   instalación;
-   auto-start;
-   health-check;
-   rotación de logs.

### Fase 5 --- Integración Remitos

En `fasa-erp-web`:

-   estación;
-   creación de job;
-   estado;
-   impresión automática;
-   reimpresión;
-   fallback manual.

### Fase 6 --- Producción controlada

-   un puesto;
-   una impresora;
-   `REMITO_CTACTE`;
-   monitoreo;
-   ampliar puestos;
-   ampliar tipos de impresión.

------------------------------------------------------------------------

## 33. Decisiones arquitectónicas ya tomadas

1.  El proyecto será **específico de FASA**.
2.  Será un repo separado de `fasa-erp-web`.
3.  El agente principal correrá en **SERVERFASA / Windows Server 2019**.
4.  No se instalará un agente en cada PC salvo que aparezca una
    necesidad técnica concreta.
5.  Las PCs cliente no necesitarán tener todas las impresoras
    instaladas.
6.  Se reutilizarán inicialmente `impresora_maquina` e `impresoras`.
7.  Se utilizará una cola persistente.
8.  El agente trabajará inicialmente mediante polling.
9.  Se conservará impresión manual como fallback.
10. El primer caso real será `REMITO_CTACTE`.
11. La solución futura **Vogel Print Services será otro proyecto**,
    moderno y desacoplado de estas tablas históricas.

------------------------------------------------------------------------

## 34. Primera tarea para el nuevo proyecto

Antes de escribir la implementación definitiva:

> Auditar el esquema real y los datos de `impresora_maquina` e
> `impresoras`, identificar cómo el VFP resuelve actualmente
> `MAQUINA + TIPO_IMPRESION → impresora`, y realizar un spike en Windows
> Server 2019 que liste las impresoras visibles e imprima un PDF A5 de
> prueba. No modificar `fasa-erp-web` hasta que esta prueba local
> funcione.

La primera entrega del nuevo repo debe demostrar que **SERVERFASA puede
imprimir correctamente un documento A5 en una impresora real de FASA sin
intervención de una PC cliente**.

------------------------------------------------------------------------

# Resultado esperado

Al finalizar la implementación:

``` text
El usuario trabaja desde cualquier PC autorizada
        ↓
abre FASA ERP Web
        ↓
genera un Remito
        ↓
el ERP conoce su estación
        ↓
crea un trabajo
        ↓
SERVERFASA lo procesa
        ↓
las tablas históricas determinan la impresora
        ↓
el documento sale automáticamente
```

Sin diálogo del navegador y sin necesidad de instalar todas las
impresoras en cada puesto.
