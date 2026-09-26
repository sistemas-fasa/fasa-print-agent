-- FASA Print Agent — cola de trabajos (SPEC §9).
-- Adaptar al esquema/migraciones reales del ERP (charset, engine, empresa_id).
CREATE TABLE IF NOT EXISTS print_jobs (
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

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
