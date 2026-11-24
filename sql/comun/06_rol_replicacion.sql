-- =====================================================================
-- Usuario de replicación (se ejecuta en los 6 nodos)
-- Las suscripciones se conectan al publicador con este usuario.
-- Necesita:
--   - el atributo REPLICATION (para abrir la conexión de replicación)
--   - SELECT sobre las tablas publicadas (para la copia inicial, copy_data).
--     Esos permisos se dan por esquema en 10_capas_por_esquema.sql
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{{REPL_USER}}') THEN
        CREATE ROLE {{REPL_USER}} WITH LOGIN REPLICATION;
    END IF;
END;
$$;

ALTER ROLE {{REPL_USER}} WITH LOGIN REPLICATION PASSWORD '{{REPL_PASSWORD}}';
