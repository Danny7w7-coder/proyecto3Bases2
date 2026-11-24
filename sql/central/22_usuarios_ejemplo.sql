-- =====================================================================
-- Nodo CENTRAL: usuarios de ejemplo (clave de todos: tec2026)
-- crear_usuario() guarda la clave con hash bcrypt. Si el usuario ya existe no hace nada.
-- =====================================================================
SELECT public.crear_usuario('cartago1',    'tec2026', 1::smallint);
SELECT public.crear_usuario('cartago2',    'tec2026', 1::smallint);
SELECT public.crear_usuario('sanjose1',    'tec2026', 2::smallint);
SELECT public.crear_usuario('sancarlos1',  'tec2026', 3::smallint);
SELECT public.crear_usuario('sancarlos2',  'tec2026', 3::smallint);
SELECT public.crear_usuario('alajuela1',   'tec2026', 4::smallint);
SELECT public.crear_usuario('limon1',      'tec2026', 5::smallint);

-- Usuario inactivo (para probar que se rechaza)
SELECT public.crear_usuario('inactivo1',   'tec2026', 3::smallint);
UPDATE public.usuarios SET activo = false WHERE usuario = 'inactivo1';
