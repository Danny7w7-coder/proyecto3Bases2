-- =====================================================================
-- Nodo CENTRAL: autenticación
--
-- Flujo del plugin de QGIS:
--   1. Se conecta al central con el rol {{LOGIN_USER}} (solo puede llamar autenticar()).
--   2. SELECT * FROM public.autenticar('usuario', 'clave').
--   3. Si es correcto, recibe el campus y los datos para conectarse a SU nodo.
--   4. Se conecta al nodo del campus con el rol de edición de ese campus.
-- =====================================================================

-- Datos de conexión de cada nodo de campus, tal como los ve QGIS (desde fuera de Docker)
CREATE TABLE IF NOT EXISTS public.campus_nodos (
    campus_id        smallint PRIMARY KEY REFERENCES public.campus (campus_id),
    host             text NOT NULL,
    puerto           integer NOT NULL,
    base             text NOT NULL,
    usuario_conexion text NOT NULL,   -- rol de edición del campus (sigtec_<campus>)
    clave_conexion   text NOT NULL    -- se entrega SOLO después de autenticar (ver DECISIONES)
);

INSERT INTO public.campus_nodos (campus_id, host, puerto, base, usuario_conexion, clave_conexion) VALUES
    (1, '{{HOST_PUBLICO}}', {{PORT_CARTAGO}},    '{{DB_NAME}}', 'sigtec_cartago',    '{{EDITOR_PASSWORD}}'),
    (2, '{{HOST_PUBLICO}}', {{PORT_SAN_JOSE}},   '{{DB_NAME}}', 'sigtec_san_jose',   '{{EDITOR_PASSWORD}}'),
    (3, '{{HOST_PUBLICO}}', {{PORT_SAN_CARLOS}}, '{{DB_NAME}}', 'sigtec_san_carlos', '{{EDITOR_PASSWORD}}'),
    (4, '{{HOST_PUBLICO}}', {{PORT_ALAJUELA}},   '{{DB_NAME}}', 'sigtec_alajuela',   '{{EDITOR_PASSWORD}}'),
    (5, '{{HOST_PUBLICO}}', {{PORT_LIMON}},      '{{DB_NAME}}', 'sigtec_limon',      '{{EDITOR_PASSWORD}}')
ON CONFLICT (campus_id) DO UPDATE SET
    host = EXCLUDED.host, puerto = EXCLUDED.puerto, base = EXCLUDED.base,
    usuario_conexion = EXCLUDED.usuario_conexion, clave_conexion = EXCLUDED.clave_conexion;

-- ---------------------------------------------------------------------
-- autenticar(usuario, clave)
--   Compara la clave con el hash bcrypt guardado: crypt(clave, hash) = hash.
--   Si es correcta devuelve una fila con el campus y los datos del nodo.
--   Si no, lanza un error. El mensaje es el mismo si el usuario no existe o si
--   la clave está mal, así no se puede adivinar qué usuarios existen.
--   SECURITY DEFINER: corre como el dueño, así el rol del plugin no necesita
--   leer la tabla usuarios.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.autenticar(p_usuario text, p_clave text)
RETURNS TABLE (usuario text, campus_id smallint, campus_nombre text, esquema text,
               host text, puerto integer, base text, usuario_conexion text, clave_conexion text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
DECLARE
    u public.usuarios%ROWTYPE;
BEGIN
    SELECT * INTO u FROM public.usuarios WHERE usuarios.usuario = p_usuario;

    IF NOT FOUND OR crypt(p_clave, u.clave_hash) <> u.clave_hash THEN
        RAISE EXCEPTION 'Usuario o contraseña incorrectos.' USING ERRCODE = 'invalid_password';
    END IF;
    IF NOT u.activo THEN
        RAISE EXCEPTION 'El usuario % está inactivo.', p_usuario USING ERRCODE = 'invalid_authorization_specification';
    END IF;

    RETURN QUERY
        SELECT u.usuario, c.campus_id, c.nombre, c.esquema,
               n.host, n.puerto, n.base, n.usuario_conexion, n.clave_conexion
        FROM public.campus c
        JOIN public.campus_nodos n ON n.campus_id = c.campus_id
        WHERE c.campus_id = u.campus_id;
END;
$$;

-- ---------------------------------------------------------------------
-- crear_usuario(usuario, clave, campus): guarda la clave con hash bcrypt
-- gen_salt('bf', 10): bcrypt con costo 10 (el valor por defecto es 6, muy bajo).
-- Cada salto de 1 duplica el tiempo que cuesta probar claves por fuerza bruta.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.crear_usuario(p_usuario text, p_clave text, p_campus smallint)
RETURNS void
LANGUAGE sql AS $$
    INSERT INTO public.usuarios (usuario, clave_hash, campus_id)
    VALUES (p_usuario, crypt(p_clave, gen_salt('bf', 10)), p_campus)
    ON CONFLICT (usuario) DO NOTHING;
$$;

-- ---------------------------------------------------------------------
-- Rol del plugin: entra al central y SOLO puede ejecutar autenticar()
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{{LOGIN_USER}}') THEN
        CREATE ROLE {{LOGIN_USER}} WITH LOGIN;
    END IF;
END;
$$;
ALTER ROLE {{LOGIN_USER}} WITH LOGIN PASSWORD '{{LOGIN_PASSWORD}}';

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON FUNCTION public.autenticar(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.crear_usuario(text, text, smallint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.autenticar(text, text) TO {{LOGIN_USER}};
