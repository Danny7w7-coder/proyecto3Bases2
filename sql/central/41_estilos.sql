-- =====================================================================
-- Nodo CENTRAL: funciones para publicar y versionar estilos
-- =====================================================================

-- ---------------------------------------------------------------------
-- publicar_estilo(capa, qml, descripcion, tipo)
--   Crea una NUEVA versión del estilo de la capa sig.<capa> y la deja vigente.
--   La versión anterior se conserva (vigente = false) por si hay que volver a ella.
--   Devuelve el número de la nueva versión.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publicar_estilo(p_capa text, p_qml text, p_descripcion text, p_tipo text)
RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    nueva integer;
BEGIN
    SELECT coalesce(max(version), 0) + 1 INTO nueva
    FROM public.layer_styles WHERE f_table_schema = 'sig' AND f_table_name = p_capa;

    -- La versión actual deja de ser la vigente
    UPDATE public.layer_styles SET vigente = false, useasdefault = false
    WHERE f_table_schema = 'sig' AND f_table_name = p_capa AND vigente;

    INSERT INTO public.layer_styles
        (f_table_catalog, f_table_schema, f_table_name, f_geometry_column,
         stylename, styleqml, useasdefault, description, type, version, vigente)
    VALUES
        ('{{DB_NAME}}', 'sig', p_capa, 'geom',
         p_capa || ' v' || nueva, p_qml::xml, true, p_descripcion, p_tipo, nueva, true);
    RETURN nueva;
END;
$$;

-- ---------------------------------------------------------------------
-- activar_version_estilo(capa, version): vuelve a una versión anterior
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.activar_version_estilo(p_capa text, p_version integer)
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.layer_styles
                   WHERE f_table_schema = 'sig' AND f_table_name = p_capa AND version = p_version) THEN
        RAISE EXCEPTION 'La capa % no tiene la versión % de estilo.', p_capa, p_version;
    END IF;
    UPDATE public.layer_styles SET vigente = false, useasdefault = false
    WHERE f_table_schema = 'sig' AND f_table_name = p_capa AND vigente;
    UPDATE public.layer_styles SET vigente = true, useasdefault = true, update_time = now()
    WHERE f_table_schema = 'sig' AND f_table_name = p_capa AND version = p_version;
END;
$$;
