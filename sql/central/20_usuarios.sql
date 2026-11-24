-- =====================================================================
-- Nodo CENTRAL: usuarios del sistema
-- La contraseña nunca se guarda en texto plano: se guarda el hash bcrypt
-- generado con crypt(clave, gen_salt('bf')) de pgcrypto.
-- (La función autenticar() y los usuarios de ejemplo se agregan en la fase 5.)
-- =====================================================================
CREATE TABLE IF NOT EXISTS public.usuarios (
    usuario    text PRIMARY KEY,
    clave_hash text NOT NULL,
    campus_id  smallint NOT NULL REFERENCES public.campus (campus_id),
    activo     boolean NOT NULL DEFAULT true,
    creado_en  timestamptz NOT NULL DEFAULT now()
);
