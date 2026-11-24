-- =====================================================================
-- Nodos de CAMPUS: rol de edición del campus (sigtec_{{NODO}})
-- Es el usuario con el que el plugin de QGIS se conecta al nodo.
--
--   LEE:      las 8 vistas sig.* y las tablas de los 5 esquemas (consulta global)
--   ESCRIBE:  SOLO a través de las vistas sig.* (los triggers INSTEAD OF deciden)
--   NO PUEDE: escribir directo en ninguna tabla, ni en la de su propio campus
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sigtec_{{NODO}}') THEN
        CREATE ROLE sigtec_{{NODO}} WITH LOGIN;
    END IF;
END;
$$;
ALTER ROLE sigtec_{{NODO}} WITH LOGIN PASSWORD '{{EDITOR_PASSWORD}}';

-- Nadie más que el dueño crea objetos en public
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Lectura: catálogos y los 5 esquemas
GRANT USAGE ON SCHEMA public, sig, cartago, san_jose, san_carlos, alajuela, limon TO sigtec_{{NODO}};
GRANT SELECT ON public.campus, public.config TO sigtec_{{NODO}};
GRANT SELECT ON ALL TABLES IN SCHEMA cartago, san_jose, san_carlos, alajuela, limon TO sigtec_{{NODO}};

-- Edición: solo las vistas (las reglas las aplican los triggers INSTEAD OF)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sig TO sigtec_{{NODO}};

-- QGIS evalúa el valor por defecto del id (nextval) antes de insertar
GRANT USAGE ON SEQUENCE {{NODO}}.seq_id TO sigtec_{{NODO}};
