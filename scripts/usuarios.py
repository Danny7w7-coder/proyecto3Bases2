"""
Gestión de los usuarios de SIG-TEC (tabla public.usuarios del nodo central).

Uso:
  python scripts/usuarios.py listar
  python scripts/usuarios.py crear <usuario> <campus> [clave]
  python scripts/usuarios.py desactivar <usuario>
  python scripts/usuarios.py activar <usuario>
  python scripts/usuarios.py clave <usuario> [clave]

<campus> puede ser el número (1 a 5) o el esquema (cartago, san_jose, san_carlos, alajuela, limon).
Si no se escribe la clave, el script la pide sin mostrarla en pantalla.

Las claves se guardan con hash bcrypt (costo 10), igual que en crear_usuario() del central.
Un usuario desactivado ya no puede ingresar desde el plugin: autenticar() lo rechaza.
"""
import getpass
import sys

import psycopg2

from comun import CAMPUS, conectar


def campus_id(texto):
    """Convierte '3' o 'san_carlos' en el número del campus. Termina con error si no existe."""
    for numero, esquema in CAMPUS:
        if texto == str(numero) or texto.lower() == esquema:
            return numero
    sys.exit(f"ERROR: campus '{texto}' no existe. Use 1-5 o uno de: {', '.join(e for _, e in CAMPUS)}")


def pedir_clave(argumentos, posicion):
    """Devuelve la clave escrita en la línea de comandos o la pide sin mostrarla."""
    if len(argumentos) > posicion:
        clave = argumentos[posicion]
    else:
        clave = getpass.getpass("Clave nueva: ")
        if getpass.getpass("Repita la clave: ") != clave:
            sys.exit("ERROR: las claves no coinciden")
    # Regla mínima para no dejar claves vacías o demasiado cortas
    if len(clave) < 6:
        sys.exit("ERROR: la clave debe tener al menos 6 caracteres")
    return clave


def ejecutar(sql, parametros=()):
    """Ejecuta una sentencia en el central y devuelve (filas, cantidad de filas afectadas)."""
    conexion = conectar("central")
    cursor = conexion.cursor()
    cursor.execute(sql, parametros)
    filas = cursor.fetchall() if cursor.description else []
    afectadas = cursor.rowcount
    conexion.close()
    return filas, afectadas


def listar():
    """Muestra todos los usuarios con su campus, si están activos y cuándo se crearon."""
    filas, _ = ejecutar("""
        SELECT u.usuario, c.nombre, CASE WHEN u.activo THEN 'sí' ELSE 'NO' END,
               to_char(u.creado_en, 'YYYY-MM-DD HH24:MI')
        FROM public.usuarios u JOIN public.campus c ON c.campus_id = u.campus_id
        ORDER BY u.campus_id, u.usuario""")
    titulos = ("usuario", "campus", "activo", "creado")
    # Ancho de cada columna según el texto más largo
    anchos = [max(len(str(f[i])) for f in filas + [titulos]) for i in range(len(titulos))]
    print("  ".join(t.ljust(a) for t, a in zip(titulos, anchos)))
    for fila in filas:
        print("  ".join(str(v).ljust(a) for v, a in zip(fila, anchos)))
    print(f"\n{len(filas)} usuarios")


def crear(usuario, campus, clave):
    """Crea un usuario activo en el campus indicado, con la clave cifrada con bcrypt."""
    # Se valida antes para dar un mensaje claro (crear_usuario() solo ignora los repetidos)
    existe, _ = ejecutar("SELECT 1 FROM public.usuarios WHERE usuario = %s", (usuario,))
    if existe:
        sys.exit(f"ERROR: el usuario '{usuario}' ya existe")
    ejecutar("SELECT public.crear_usuario(%s, %s, %s::smallint)", (usuario, clave, campus))
    print(f"Usuario '{usuario}' creado en el campus {campus}.")


def cambiar_activo(usuario, activo):
    """Activa o desactiva un usuario. Sus datos y su clave no se borran."""
    _, afectadas = ejecutar("UPDATE public.usuarios SET activo = %s WHERE usuario = %s", (activo, usuario))
    if afectadas == 0:
        sys.exit(f"ERROR: el usuario '{usuario}' no existe")
    print(f"Usuario '{usuario}' {'activado' if activo else 'desactivado'}.")


def cambiar_clave(usuario, clave):
    """Cambia la clave de un usuario. Se guarda con un hash bcrypt nuevo."""
    _, afectadas = ejecutar("UPDATE public.usuarios SET clave_hash = crypt(%s, gen_salt('bf', 10)) "
                            "WHERE usuario = %s", (clave, usuario))
    if afectadas == 0:
        sys.exit(f"ERROR: el usuario '{usuario}' no existe")
    print(f"Clave de '{usuario}' cambiada.")


def main():
    """Lee el comando y sus datos de la línea de comandos y llama a la función que corresponde."""
    argumentos = sys.argv[1:]
    comando = argumentos[0] if argumentos else ""
    try:
        if comando == "listar":
            listar()
        elif comando == "crear" and len(argumentos) >= 3:
            crear(argumentos[1], campus_id(argumentos[2]), pedir_clave(argumentos, 3))
        elif comando in ("activar", "desactivar") and len(argumentos) == 2:
            cambiar_activo(argumentos[1], comando == "activar")
        elif comando == "clave" and len(argumentos) >= 2:
            cambiar_clave(argumentos[1], pedir_clave(argumentos, 2))
        else:
            # Comando desconocido o faltan datos: se muestra la ayuda de arriba
            print(__doc__)
            sys.exit(1)
    except psycopg2.OperationalError as error:
        sys.exit(f"ERROR: no se pudo conectar al nodo central. ¿Están levantados los servidores?\n{error}")


if __name__ == "__main__":
    main()
