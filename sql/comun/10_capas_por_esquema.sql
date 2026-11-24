-- =====================================================================
-- Las 8 capas geográficas de UN campus.
-- init_all.py ejecuta este archivo 5 veces en cada nodo, una por esquema:
--   {{ESQUEMA}}    = nombre del esquema (cartago, san_jose, ...)
--   {{ESQUEMA_ID}} = campus dueño de ese esquema (1 a 5)
--   {{SRID}}       = SRID institucional (5367, CRTM05)
--
-- Columnas comunes a todas las capas:
--   id            identificador global (ver secuencia abajo)
--   campus_id     campus dueño. El CHECK obliga a que sea el dueño del esquema
--   geom          geometría en el SRID institucional, con índice GIST
--   creado_en, modificado_en   auditoría simple
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS {{ESQUEMA}};

-- Secuencia del campus: cada campus usa su propio rango de ids.
--   Cartago 1 000 001 .. 1 999 999,  San José 2 000 001 .. 2 999 999,  etc.
-- Así un id nunca se repite entre campus ni entre capas.
CREATE SEQUENCE IF NOT EXISTS {{ESQUEMA}}.seq_id
    MINVALUE {{ESQUEMA_ID}}000001
    MAXVALUE {{ESQUEMA_ID}}999999
    START    {{ESQUEMA_ID}}000001;

-- ---------------------------------------------------------------------
-- 1. Edificios (Polygon)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.edificios (
    id            bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id     smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                  CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    nombre        text NOT NULL,
    codigo        text,
    area          numeric(10,2) CHECK (area > 0),          -- metros cuadrados
    pisos         smallint CHECK (pisos > 0),
    geom          geometry(Polygon, {{SRID}}) NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    modificado_en timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 2. Carreteras (LineString)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.carreteras (
    id            bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id     smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                  CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    nombre        text,
    tipo          text CHECK (tipo IN ('principal', 'secundaria', 'interna', 'servicio')),
    superficie    text CHECK (superficie IN ('asfalto', 'concreto', 'lastre', 'adoquin')),
    geom          geometry(LineString, {{SRID}}) NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    modificado_en timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 3. Aceras (LineString)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.aceras (
    id            bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id     smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                  CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    material      text CHECK (material IN ('concreto', 'adoquin', 'asfalto', 'lastre')),
    ancho         numeric(4,2) CHECK (ancho > 0),          -- metros
    condicion     text CHECK (condicion IN ('buena', 'regular', 'mala')),
    geom          geometry(LineString, {{SRID}}) NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    modificado_en timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 4. Parqueos (Polygon)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.parqueos (
    id             bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id      smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                   CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    nombre         text,
    capacidad      integer CHECK (capacidad >= 0),         -- espacios totales
    tipo           text CHECK (tipo IN ('estudiantes', 'funcionarios', 'visitantes', 'motos', 'discapacidad')),
    disponibilidad integer,                                -- espacios libres
    geom           geometry(Polygon, {{SRID}}) NOT NULL,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    modificado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_disponibilidad CHECK (disponibilidad BETWEEN 0 AND capacidad)
);

-- ---------------------------------------------------------------------
-- 5. Zonas verdes (Polygon)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.zonas_verdes (
    id              bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id       smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                    CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    nombre          text,
    area            numeric(10,2) CHECK (area > 0),        -- metros cuadrados
    tipo_vegetacion text CHECK (tipo_vegetacion IN ('cesped', 'jardin', 'arboles', 'bosque', 'mixta')),
    geom            geometry(Polygon, {{SRID}}) NOT NULL,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    modificado_en   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 6. Puntos de interés (Point): cajeros, laboratorios, sodas, ...
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.puntos_interes (
    id            bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id     smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                  CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    nombre        text NOT NULL,
    tipo          text NOT NULL CHECK (tipo IN ('cajero', 'laboratorio', 'soda', 'biblioteca', 'parada_bus', 'otro')),
    descripcion   text,
    geom          geometry(Point, {{SRID}}) NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    modificado_en timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 7. Iluminación (Point)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.iluminacion (
    id            bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id     smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                  CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    codigo        text,
    potencia      integer CHECK (potencia > 0),           -- watts
    estado        text CHECK (estado IN ('funcionando', 'danada', 'mantenimiento')),
    geom          geometry(Point, {{SRID}}) NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    modificado_en timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 8. Accesibilidad (LineString): rampas, pasos accesibles
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {{ESQUEMA}}.accesibilidad (
    id            bigint PRIMARY KEY DEFAULT nextval('{{ESQUEMA}}.seq_id'),
    campus_id     smallint NOT NULL DEFAULT {{ESQUEMA_ID}}
                  CONSTRAINT ck_campus_dueno CHECK (campus_id = {{ESQUEMA_ID}}),
    tipo          text NOT NULL CHECK (tipo IN ('rampa', 'paso_accesible', 'ruta_podotactil', 'elevador')),
    descripcion   text,
    geom          geometry(LineString, {{SRID}}) NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    modificado_en timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Índices espaciales GIST (uno por capa)
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS edificios_geom_gist      ON {{ESQUEMA}}.edificios      USING gist (geom);
CREATE INDEX IF NOT EXISTS carreteras_geom_gist     ON {{ESQUEMA}}.carreteras     USING gist (geom);
CREATE INDEX IF NOT EXISTS aceras_geom_gist         ON {{ESQUEMA}}.aceras         USING gist (geom);
CREATE INDEX IF NOT EXISTS parqueos_geom_gist       ON {{ESQUEMA}}.parqueos       USING gist (geom);
CREATE INDEX IF NOT EXISTS zonas_verdes_geom_gist   ON {{ESQUEMA}}.zonas_verdes   USING gist (geom);
CREATE INDEX IF NOT EXISTS puntos_interes_geom_gist ON {{ESQUEMA}}.puntos_interes USING gist (geom);
CREATE INDEX IF NOT EXISTS iluminacion_geom_gist    ON {{ESQUEMA}}.iluminacion    USING gist (geom);
CREATE INDEX IF NOT EXISTS accesibilidad_geom_gist  ON {{ESQUEMA}}.accesibilidad  USING gist (geom);

-- ---------------------------------------------------------------------
-- Replicación lógica
--  - REPLICA IDENTITY: se usa la clave primaria (id), que es el valor por defecto.
--    Con ella el suscriptor sabe qué fila actualizar o borrar.
--  - El usuario de replicación necesita leer las tablas para la copia inicial.
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA {{ESQUEMA}} TO {{REPL_USER}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{ESQUEMA}} TO {{REPL_USER}};

-- ---------------------------------------------------------------------
-- Trigger de protección: solo el nodo dueño escribe en este esquema.
-- Es por sentencia (FOR EACH STATEMENT) porque no depende de la fila:
-- basta saber en qué nodo estamos. Cubre también TRUNCATE.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.edificios      FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.carreteras     FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.aceras         FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.parqueos       FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.zonas_verdes   FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.puntos_interes FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.iluminacion    FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});
CREATE OR REPLACE TRIGGER tg_solo_dueno BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {{ESQUEMA}}.accesibilidad  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_solo_dueno({{ESQUEMA_ID}});

-- ---------------------------------------------------------------------
-- Trigger de auditoría: actualiza modificado_en en cada UPDATE
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.edificios      FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.carreteras     FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.aceras         FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.parqueos       FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.zonas_verdes   FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.puntos_interes FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.iluminacion    FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
CREATE OR REPLACE TRIGGER tg_modificado_en BEFORE UPDATE ON {{ESQUEMA}}.accesibilidad  FOR EACH ROW EXECUTE FUNCTION public.fn_modificado_en();
