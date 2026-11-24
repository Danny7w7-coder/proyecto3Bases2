-- =====================================================================
-- Estilos de QGIS guardados en la base de datos (se ejecuta en los 6 nodos)
--
-- Estructura estándar de QGIS (la misma que crea "Guardar estilo en la base de datos"),
-- más dos columnas para manejar versiones:
--   version  número de versión del estilo de esa capa (1, 2, 3, ...)
--   vigente  true en la versión que se usa ahora. useasdefault sigue a vigente.
--
-- Los estilos se crean SOLO en el nodo central y llegan a los campus por
-- replicación lógica (van en las publicaciones del nivel 2).
-- En los campus la tabla es de solo lectura (trigger abajo).
-- =====================================================================
CREATE TABLE IF NOT EXISTS public.layer_styles (
    id                serial PRIMARY KEY,
    f_table_catalog   varchar,             -- nombre de la base (sigtec)
    f_table_schema    varchar,             -- esquema de la capa (sig)
    f_table_name      varchar,             -- vista (edificios, carreteras, ...)
    f_geometry_column varchar,             -- geom
    stylename         text,
    styleqml          xml,
    stylesld          xml,
    useasdefault      boolean,
    description       text,
    owner             varchar(63) DEFAULT CURRENT_USER,
    ui                xml,
    update_time       timestamp DEFAULT CURRENT_TIMESTAMP,
    type              varchar,             -- Point, Line o Polygon
    -- columnas propias de SIG-TEC
    version           integer NOT NULL DEFAULT 1,
    vigente           boolean NOT NULL DEFAULT true
);

-- Solo puede haber UNA versión vigente por capa
CREATE UNIQUE INDEX IF NOT EXISTS layer_styles_una_vigente
    ON public.layer_styles (f_table_schema, f_table_name) WHERE vigente;

-- En los campus nadie escribe en layer_styles: se administra en el central.
-- (No afecta a la replicación: el trigger no se dispara con datos replicados.)
CREATE OR REPLACE FUNCTION public.fn_estilos_solo_central() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF public.mi_campus() IS NOT NULL THEN
        RAISE EXCEPTION 'Los estilos se administran en el nodo central. En este nodo son de solo lectura.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE TRIGGER tg_estilos_solo_central
    BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON public.layer_styles
    FOR EACH STATEMENT EXECUTE FUNCTION public.fn_estilos_solo_central();

-- La replicación necesita leer la tabla para la copia inicial
GRANT SELECT ON public.layer_styles TO {{REPL_USER}};
