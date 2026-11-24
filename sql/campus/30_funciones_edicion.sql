-- =====================================================================
-- Nodos de CAMPUS: funciones de apoyo para los triggers INSTEAD OF
-- {{NODO}} = esquema propio de este nodo (cartago, san_jose, ...)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS sig;  -- aquí viven las vistas que carga QGIS

-- ---------------------------------------------------------------------
-- normalizar_geom: deja una geometría lista para guardarla
--   1. Sin SRID (0)        -> se asume el institucional ({{SRID}})
--   2. Con otro SRID       -> se convierte con ST_Transform (ej. 4326 -> {{SRID}})
--   3. Multi de una parte  -> se pasa a simple (QGIS a veces envía MultiPolygon)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.normalizar_geom(g geometry) RETURNS geometry
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF g IS NULL THEN
        RETURN NULL;
    END IF;
    IF ST_SRID(g) = 0 THEN
        g := ST_SetSRID(g, {{SRID}});
    ELSIF ST_SRID(g) <> {{SRID}} THEN
        g := ST_Transform(g, {{SRID}});
    END IF;
    IF GeometryType(g) LIKE 'MULTI%' AND ST_NumGeometries(g) = 1 THEN
        g := ST_GeometryN(g, 1);
    END IF;
    RETURN g;
END;
$$;

-- ---------------------------------------------------------------------
-- validar_dueno: lanza un error claro si la fila no es del campus de este nodo
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.validar_dueno(fila_campus smallint, fila_id bigint, operacion text)
RETURNS void
LANGUAGE plpgsql STABLE AS $$
DECLARE
    accion text := CASE operacion WHEN 'UPDATE' THEN 'modificar' ELSE 'eliminar' END;
    dueno  text;
    yo     text;
BEGIN
    IF fila_campus IS DISTINCT FROM public.mi_campus() THEN
        SELECT nombre INTO dueno FROM public.campus WHERE campus_id = fila_campus;
        SELECT nombre INTO yo    FROM public.campus WHERE campus_id = public.mi_campus();
        RAISE EXCEPTION 'No puede % el objeto % porque pertenece al %. Desde este nodo solo se editan objetos del %.',
            accion, fila_id, dueno, yo
            USING ERRCODE = 'insufficient_privilege';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- validar_llave: en un UPDATE no se puede cambiar el id ni el campus
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.validar_llave(viejo_id bigint, nuevo_id bigint,
                                                viejo_campus smallint, nuevo_campus smallint)
RETURNS void
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF nuevo_id IS DISTINCT FROM viejo_id THEN
        RAISE EXCEPTION 'No se puede cambiar el id de un objeto (%).', viejo_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF nuevo_campus IS DISTINCT FROM viejo_campus THEN
        RAISE EXCEPTION 'No se puede cambiar el campus de un objeto (%). Cada objeto pertenece siempre a su campus.', viejo_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- nuevo_id: usa el id que viene si es del rango de este campus, si no toma uno nuevo
-- (QGIS puede pedir el valor por defecto de la vista antes de insertar)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.nuevo_id(id_propuesto bigint) RETURNS bigint
LANGUAGE plpgsql AS $$
BEGIN
    IF id_propuesto IS NOT NULL AND id_propuesto / 1000000 = public.mi_campus() THEN
        RETURN id_propuesto;
    END IF;
    RETURN nextval('{{NODO}}.seq_id');
END;
$$;
