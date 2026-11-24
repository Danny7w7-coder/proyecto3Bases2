-- =====================================================================
-- Configuración del nodo (se ejecuta en los 6 nodos)
-- =====================================================================

-- Catálogo de los 5 campus. Es igual en todos los nodos.
CREATE TABLE IF NOT EXISTS public.campus (
    campus_id smallint PRIMARY KEY CHECK (campus_id BETWEEN 1 AND 5),
    esquema   text NOT NULL UNIQUE,   -- nombre del esquema donde viven sus capas
    nombre    text NOT NULL           -- nombre para mostrar
);

INSERT INTO public.campus (campus_id, esquema, nombre) VALUES
    (1, 'cartago',    'Campus Tecnológico Central Cartago'),
    (2, 'san_jose',   'Campus Tecnológico Local San José'),
    (3, 'san_carlos', 'Campus Tecnológico Local San Carlos'),
    (4, 'alajuela',   'Campus Tecnológico Local Alajuela'),
    (5, 'limon',      'Campus Tecnológico Local Limón')
ON CONFLICT (campus_id) DO NOTHING;

-- "¿Quién soy?": una sola fila con el campus de este nodo.
-- En el nodo central campus_id es NULL porque no es dueño de ningún campus.
CREATE TABLE IF NOT EXISTS public.config (
    unica     boolean PRIMARY KEY DEFAULT true CHECK (unica),  -- obliga a tener una sola fila
    nodo      text NOT NULL,
    campus_id smallint REFERENCES public.campus (campus_id)
);

INSERT INTO public.config (nodo, campus_id) VALUES ('{{NODO}}', {{CAMPUS_ID}})
ON CONFLICT (unica) DO UPDATE SET nodo = EXCLUDED.nodo, campus_id = EXCLUDED.campus_id;

-- Devuelve el campus de este nodo (NULL en el central). La usan los triggers.
CREATE OR REPLACE FUNCTION public.mi_campus() RETURNS smallint
LANGUAGE sql STABLE AS $$
    SELECT campus_id FROM public.config;
$$;

-- Trigger de protección de réplicas: solo el nodo dueño puede escribir en un esquema.
-- Recibe como argumento (TG_ARGV[0]) el campus dueño del esquema de la tabla.
--   - En el nodo de San Carlos (mi_campus = 3) se puede escribir en san_carlos.*,
--     pero no en cartago.*, san_jose.*, etc. (son copias de consulta).
--   - En el central (mi_campus = NULL) no se puede escribir en ningún esquema:
--     todo lo recibe por replicación.
-- Este trigger NO se dispara cuando la fila llega por replicación lógica (el proceso de
-- replicación trabaja con session_replication_role = replica), así que no la bloquea.
CREATE OR REPLACE FUNCTION public.fn_solo_dueno() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    dueno smallint := TG_ARGV[0]::smallint;
BEGIN
    IF public.mi_campus() IS DISTINCT FROM dueno THEN
        RAISE EXCEPTION 'El esquema % es una copia de solo lectura en el nodo %. Solo el campus % puede modificarlo.',
            TG_TABLE_SCHEMA, (SELECT nodo FROM public.config), dueno;
    END IF;
    RETURN NULL;  -- en un trigger por sentencia el valor de retorno se ignora
END;
$$;

-- Trigger genérico: actualiza la columna modificado_en en cada UPDATE.
-- Nota: los triggers normales NO se disparan cuando la fila llega por replicación
-- lógica, así que en las réplicas se conserva la fecha del campus dueño.
CREATE OR REPLACE FUNCTION public.fn_modificado_en() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.modificado_en := now();
    RETURN NEW;
END;
$$;
