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
