-- =====================================================================
-- Nodos de CAMPUS: vistas distribuidas + triggers INSTEAD OF
-- {{NODO}} = esquema propio de este nodo. {{CAMPUS_ID}} = su campus.
--
-- Cada vista sig.<capa> junta con UNION ALL la tabla local (editable) y las
-- 4 réplicas de los otros campus. QGIS carga UNA capa por tema.
--
-- Los triggers INSTEAD OF deciden qué pasa cuando QGIS edita la vista:
--   INSERT -> se guarda en la tabla del campus de ESTE nodo, con su campus_id,
--             un id de su secuencia y la geometría en el SRID institucional.
--   UPDATE -> solo si el objeto es de este campus. No se puede cambiar id ni campus.
--   DELETE -> solo si el objeto es de este campus.
--
-- Las funciones son SECURITY DEFINER: corren con los permisos de su dueño (postgres).
-- Así el rol de edición del campus NO necesita permiso directo sobre las tablas:
-- solo puede escribir a través de las vistas y sus reglas.
--
-- geom se expone como "geometry" genérico (sin tipo ni SRID) para que una
-- geometría en otro SRID (ej. 4326) llegue al trigger y se pueda transformar.
-- =====================================================================


-- =====================================================================
-- 1. EDIFICIOS
-- =====================================================================
CREATE OR REPLACE VIEW sig.edificios AS
          SELECT id, campus_id, nombre, codigo, area, pisos, creado_en, modificado_en, geom::geometry AS geom FROM cartago.edificios
UNION ALL SELECT id, campus_id, nombre, codigo, area, pisos, creado_en, modificado_en, geom::geometry FROM san_jose.edificios
UNION ALL SELECT id, campus_id, nombre, codigo, area, pisos, creado_en, modificado_en, geom::geometry FROM san_carlos.edificios
UNION ALL SELECT id, campus_id, nombre, codigo, area, pisos, creado_en, modificado_en, geom::geometry FROM alajuela.edificios
UNION ALL SELECT id, campus_id, nombre, codigo, area, pisos, creado_en, modificado_en, geom::geometry FROM limon.edificios;

CREATE OR REPLACE FUNCTION sig.tg_edificios() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.edificios (id, campus_id, nombre, codigo, area, pisos, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.nombre, NEW.codigo, NEW.area, NEW.pisos, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.edificios
           SET nombre = NEW.nombre, codigo = NEW.codigo, area = NEW.area, pisos = NEW.pisos, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.edificios WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.edificios
    FOR EACH ROW EXECUTE FUNCTION sig.tg_edificios();


-- =====================================================================
-- 2. CARRETERAS
-- =====================================================================
CREATE OR REPLACE VIEW sig.carreteras AS
          SELECT id, campus_id, nombre, tipo, superficie, creado_en, modificado_en, geom::geometry AS geom FROM cartago.carreteras
UNION ALL SELECT id, campus_id, nombre, tipo, superficie, creado_en, modificado_en, geom::geometry FROM san_jose.carreteras
UNION ALL SELECT id, campus_id, nombre, tipo, superficie, creado_en, modificado_en, geom::geometry FROM san_carlos.carreteras
UNION ALL SELECT id, campus_id, nombre, tipo, superficie, creado_en, modificado_en, geom::geometry FROM alajuela.carreteras
UNION ALL SELECT id, campus_id, nombre, tipo, superficie, creado_en, modificado_en, geom::geometry FROM limon.carreteras;

CREATE OR REPLACE FUNCTION sig.tg_carreteras() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.carreteras (id, campus_id, nombre, tipo, superficie, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.nombre, NEW.tipo, NEW.superficie, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.carreteras
           SET nombre = NEW.nombre, tipo = NEW.tipo, superficie = NEW.superficie, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.carreteras WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.carreteras
    FOR EACH ROW EXECUTE FUNCTION sig.tg_carreteras();


-- =====================================================================
-- 3. ACERAS
-- =====================================================================
CREATE OR REPLACE VIEW sig.aceras AS
          SELECT id, campus_id, material, ancho, condicion, creado_en, modificado_en, geom::geometry AS geom FROM cartago.aceras
UNION ALL SELECT id, campus_id, material, ancho, condicion, creado_en, modificado_en, geom::geometry FROM san_jose.aceras
UNION ALL SELECT id, campus_id, material, ancho, condicion, creado_en, modificado_en, geom::geometry FROM san_carlos.aceras
UNION ALL SELECT id, campus_id, material, ancho, condicion, creado_en, modificado_en, geom::geometry FROM alajuela.aceras
UNION ALL SELECT id, campus_id, material, ancho, condicion, creado_en, modificado_en, geom::geometry FROM limon.aceras;

CREATE OR REPLACE FUNCTION sig.tg_aceras() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.aceras (id, campus_id, material, ancho, condicion, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.material, NEW.ancho, NEW.condicion, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.aceras
           SET material = NEW.material, ancho = NEW.ancho, condicion = NEW.condicion, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.aceras WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.aceras
    FOR EACH ROW EXECUTE FUNCTION sig.tg_aceras();


-- =====================================================================
-- 4. PARQUEOS
-- =====================================================================
CREATE OR REPLACE VIEW sig.parqueos AS
          SELECT id, campus_id, nombre, capacidad, tipo, disponibilidad, creado_en, modificado_en, geom::geometry AS geom FROM cartago.parqueos
UNION ALL SELECT id, campus_id, nombre, capacidad, tipo, disponibilidad, creado_en, modificado_en, geom::geometry FROM san_jose.parqueos
UNION ALL SELECT id, campus_id, nombre, capacidad, tipo, disponibilidad, creado_en, modificado_en, geom::geometry FROM san_carlos.parqueos
UNION ALL SELECT id, campus_id, nombre, capacidad, tipo, disponibilidad, creado_en, modificado_en, geom::geometry FROM alajuela.parqueos
UNION ALL SELECT id, campus_id, nombre, capacidad, tipo, disponibilidad, creado_en, modificado_en, geom::geometry FROM limon.parqueos;

CREATE OR REPLACE FUNCTION sig.tg_parqueos() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.parqueos (id, campus_id, nombre, capacidad, tipo, disponibilidad, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.nombre, NEW.capacidad, NEW.tipo, NEW.disponibilidad, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.parqueos
           SET nombre = NEW.nombre, capacidad = NEW.capacidad, tipo = NEW.tipo,
               disponibilidad = NEW.disponibilidad, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.parqueos WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.parqueos
    FOR EACH ROW EXECUTE FUNCTION sig.tg_parqueos();


-- =====================================================================
-- 5. ZONAS VERDES
-- =====================================================================
CREATE OR REPLACE VIEW sig.zonas_verdes AS
          SELECT id, campus_id, nombre, area, tipo_vegetacion, creado_en, modificado_en, geom::geometry AS geom FROM cartago.zonas_verdes
UNION ALL SELECT id, campus_id, nombre, area, tipo_vegetacion, creado_en, modificado_en, geom::geometry FROM san_jose.zonas_verdes
UNION ALL SELECT id, campus_id, nombre, area, tipo_vegetacion, creado_en, modificado_en, geom::geometry FROM san_carlos.zonas_verdes
UNION ALL SELECT id, campus_id, nombre, area, tipo_vegetacion, creado_en, modificado_en, geom::geometry FROM alajuela.zonas_verdes
UNION ALL SELECT id, campus_id, nombre, area, tipo_vegetacion, creado_en, modificado_en, geom::geometry FROM limon.zonas_verdes;

CREATE OR REPLACE FUNCTION sig.tg_zonas_verdes() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.zonas_verdes (id, campus_id, nombre, area, tipo_vegetacion, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.nombre, NEW.area, NEW.tipo_vegetacion, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.zonas_verdes
           SET nombre = NEW.nombre, area = NEW.area, tipo_vegetacion = NEW.tipo_vegetacion, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.zonas_verdes WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.zonas_verdes
    FOR EACH ROW EXECUTE FUNCTION sig.tg_zonas_verdes();


-- =====================================================================
-- 6. PUNTOS DE INTERÉS
-- =====================================================================
CREATE OR REPLACE VIEW sig.puntos_interes AS
          SELECT id, campus_id, nombre, tipo, descripcion, creado_en, modificado_en, geom::geometry AS geom FROM cartago.puntos_interes
UNION ALL SELECT id, campus_id, nombre, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM san_jose.puntos_interes
UNION ALL SELECT id, campus_id, nombre, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM san_carlos.puntos_interes
UNION ALL SELECT id, campus_id, nombre, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM alajuela.puntos_interes
UNION ALL SELECT id, campus_id, nombre, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM limon.puntos_interes;

CREATE OR REPLACE FUNCTION sig.tg_puntos_interes() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.puntos_interes (id, campus_id, nombre, tipo, descripcion, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.nombre, NEW.tipo, NEW.descripcion, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.puntos_interes
           SET nombre = NEW.nombre, tipo = NEW.tipo, descripcion = NEW.descripcion, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.puntos_interes WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.puntos_interes
    FOR EACH ROW EXECUTE FUNCTION sig.tg_puntos_interes();


-- =====================================================================
-- 7. ILUMINACIÓN
-- =====================================================================
CREATE OR REPLACE VIEW sig.iluminacion AS
          SELECT id, campus_id, codigo, potencia, estado, creado_en, modificado_en, geom::geometry AS geom FROM cartago.iluminacion
UNION ALL SELECT id, campus_id, codigo, potencia, estado, creado_en, modificado_en, geom::geometry FROM san_jose.iluminacion
UNION ALL SELECT id, campus_id, codigo, potencia, estado, creado_en, modificado_en, geom::geometry FROM san_carlos.iluminacion
UNION ALL SELECT id, campus_id, codigo, potencia, estado, creado_en, modificado_en, geom::geometry FROM alajuela.iluminacion
UNION ALL SELECT id, campus_id, codigo, potencia, estado, creado_en, modificado_en, geom::geometry FROM limon.iluminacion;

CREATE OR REPLACE FUNCTION sig.tg_iluminacion() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.iluminacion (id, campus_id, codigo, potencia, estado, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.codigo, NEW.potencia, NEW.estado, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.iluminacion
           SET codigo = NEW.codigo, potencia = NEW.potencia, estado = NEW.estado, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.iluminacion WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.iluminacion
    FOR EACH ROW EXECUTE FUNCTION sig.tg_iluminacion();


-- =====================================================================
-- 8. ACCESIBILIDAD
-- =====================================================================
CREATE OR REPLACE VIEW sig.accesibilidad AS
          SELECT id, campus_id, tipo, descripcion, creado_en, modificado_en, geom::geometry AS geom FROM cartago.accesibilidad
UNION ALL SELECT id, campus_id, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM san_jose.accesibilidad
UNION ALL SELECT id, campus_id, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM san_carlos.accesibilidad
UNION ALL SELECT id, campus_id, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM alajuela.accesibilidad
UNION ALL SELECT id, campus_id, tipo, descripcion, creado_en, modificado_en, geom::geometry FROM limon.accesibilidad;

CREATE OR REPLACE FUNCTION sig.tg_accesibilidad() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.campus_id := public.mi_campus();
        NEW.id        := public.nuevo_id(NEW.id);
        NEW.geom      := public.normalizar_geom(NEW.geom);
        INSERT INTO {{NODO}}.accesibilidad (id, campus_id, tipo, descripcion, geom)
        VALUES (NEW.id, NEW.campus_id, NEW.tipo, NEW.descripcion, NEW.geom)
        RETURNING creado_en, modificado_en INTO NEW.creado_en, NEW.modificado_en;
        RETURN NEW;
    END IF;

    PERFORM public.validar_dueno(OLD.campus_id, OLD.id, TG_OP);

    IF TG_OP = 'UPDATE' THEN
        PERFORM public.validar_llave(OLD.id, NEW.id, OLD.campus_id, NEW.campus_id);
        NEW.geom := public.normalizar_geom(NEW.geom);
        UPDATE {{NODO}}.accesibilidad
           SET tipo = NEW.tipo, descripcion = NEW.descripcion, geom = NEW.geom
         WHERE id = OLD.id
        RETURNING modificado_en INTO NEW.modificado_en;
        RETURN NEW;
    END IF;

    DELETE FROM {{NODO}}.accesibilidad WHERE id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER tg_editar INSTEAD OF INSERT OR UPDATE OR DELETE ON sig.accesibilidad
    FOR EACH ROW EXECUTE FUNCTION sig.tg_accesibilidad();


-- =====================================================================
-- Valores por defecto en las vistas (los usa QGIS al crear un objeto nuevo)
-- =====================================================================
ALTER VIEW sig.edificios      ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.carreteras     ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.aceras         ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.parqueos       ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.zonas_verdes   ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.puntos_interes ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.iluminacion    ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};
ALTER VIEW sig.accesibilidad  ALTER COLUMN campus_id SET DEFAULT {{CAMPUS_ID}};

ALTER VIEW sig.edificios      ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.carreteras     ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.aceras         ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.parqueos       ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.zonas_verdes   ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.puntos_interes ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.iluminacion    ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
ALTER VIEW sig.accesibilidad  ALTER COLUMN id SET DEFAULT nextval('{{NODO}}.seq_id');
