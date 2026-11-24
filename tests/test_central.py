"""
Pruebas de la fase 5: autenticación en el nodo central y estilos (layer_styles).
"""
import os
import sys
import xml.etree.ElementTree as ET

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import generar_estilos  # noqa: E402
from cargar_datos import CAPAS  # noqa: E402
from comun import CAMPUS, ENV, NODOS, conectar, contar, esperar_hasta  # noqa: E402

CLAVE_EJEMPLO = "tec2026"


def autenticar(usuario, clave):
    """Llama a autenticar() como lo hará el plugin. Devuelve (fila, None) o (None, mensaje)."""
    conexion = conectar("central", usuario=ENV["LOGIN_USER"], clave=ENV["LOGIN_PASSWORD"])
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT * FROM public.autenticar(%s, %s)", (usuario, clave))
        columnas = [c.name for c in cursor.description]
        return dict(zip(columnas, cursor.fetchone())), None
    except psycopg2.Error as error:
        return None, error.diag.message_primary
    finally:
        conexion.close()


# ---------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------
def prueba_login_correcto_por_campus():
    """Credenciales correctas: devuelve el campus y el nodo correcto (un usuario por campus)"""
    usuarios = {"cartago1": 1, "sanjose1": 2, "sancarlos1": 3, "alajuela1": 4, "limon1": 5}
    for usuario, campus_id in usuarios.items():
        datos, error = autenticar(usuario, CLAVE_EJEMPLO)
        assert error is None, f"{usuario}: {error}"
        esquema = dict(CAMPUS)[campus_id]
        assert datos["campus_id"] == campus_id and datos["esquema"] == esquema, datos
        assert datos["puerto"] == NODOS[esquema]["puerto"], f"{usuario}: puerto {datos['puerto']}"
    return "5 campus"


def prueba_login_incorrecto():
    """Clave mala o usuario inexistente: mismo mensaje de error (no revela si el usuario existe)"""
    _, error_clave = autenticar("sancarlos1", "otra_clave")
    _, error_usuario = autenticar("no_existe", CLAVE_EJEMPLO)
    assert error_clave == error_usuario == "Usuario o contraseña incorrectos.", (error_clave, error_usuario)
    return error_clave


def prueba_login_inactivo():
    """Un usuario inactivo no puede entrar aunque la clave sea correcta"""
    _, error = autenticar("inactivo1", CLAVE_EJEMPLO)
    assert error and "inactivo" in error, error


def prueba_claves_con_hash():
    """Las claves se guardan con hash bcrypt (costo 10), nunca en texto plano"""
    # %% es un % literal (psycopg2 usa % para los parámetros)
    filas = contar("central", "SELECT count(*) FROM public.usuarios WHERE clave_hash NOT LIKE '$2a$10$%%' "
                              "OR clave_hash = %s", (CLAVE_EJEMPLO,))
    assert filas == 0, f"{filas} usuarios sin hash bcrypt"
    return contar("central", "SELECT left(clave_hash, 20) || '...' FROM public.usuarios WHERE usuario = 'sancarlos1'")


def prueba_rol_login_restringido():
    """El rol del plugin solo puede llamar autenticar(): no puede leer usuarios ni campus_nodos"""
    conexion = conectar("central", usuario=ENV["LOGIN_USER"], clave=ENV["LOGIN_PASSWORD"])
    cursor = conexion.cursor()
    for tabla in ["public.usuarios", "public.campus_nodos"]:
        try:
            cursor.execute(f"SELECT * FROM {tabla}")
            raise AssertionError(f"pudo leer {tabla}")
        except psycopg2.errors.InsufficientPrivilege:
            pass
    conexion.close()


def prueba_datos_nodo_sirven():
    """Con los datos que devuelve autenticar() se puede entrar al nodo del campus y leer las vistas"""
    datos, _ = autenticar("sancarlos1", CLAVE_EJEMPLO)
    conexion = psycopg2.connect(host="127.0.0.1" if datos["host"] == "localhost" else datos["host"],
                                port=datos["puerto"], dbname=datos["base"],
                                user=datos["usuario_conexion"], password=datos["clave_conexion"])
    cursor = conexion.cursor()
    cursor.execute("SELECT public.mi_campus(), count(*) FROM sig.edificios")
    mi_campus, total = cursor.fetchone()
    conexion.close()
    assert mi_campus == 3 and total > 0
    return f"conectado como {datos['usuario_conexion']} al puerto {datos['puerto']}"


# ---------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------
def prueba_estilos_en_todos_los_nodos():
    """Las 8 capas tienen un estilo vigente en el central y en los 5 campus (replicado)"""
    for nodo in NODOS:
        vigentes = contar(nodo, "SELECT count(*) FROM public.layer_styles WHERE vigente AND useasdefault "
                                "AND f_table_schema = 'sig' AND f_geometry_column = 'geom' "
                                "AND f_table_catalog = %s", (ENV["DB_NAME"],))
        assert vigentes == len(CAPAS), f"{nodo}: {vigentes} estilos vigentes"
    return "8 estilos x 6 nodos"


def prueba_qml_valido():
    """Cada QML es XML válido con raíz <qgis> y un renderer"""
    conexion = conectar("san_carlos")
    cursor = conexion.cursor()
    cursor.execute("SELECT f_table_name, styleqml::text FROM public.layer_styles WHERE vigente")
    for capa, texto in cursor.fetchall():
        raiz = ET.fromstring(texto)
        assert raiz.tag == "qgis" and raiz.find("renderer-v2") is not None, capa
    conexion.close()


def prueba_version_nueva_y_volver():
    """Nueva versión de un estilo: se replica a los campus y se puede volver a la anterior"""
    sql = "SELECT version FROM public.layer_styles WHERE f_table_name = 'parqueos' AND vigente"
    anterior = contar("central", sql)
    try:
        nueva = generar_estilos.publicar("parqueos", "200,90,90", "Prueba de versión")
        segundos = esperar_hasta(lambda: all(contar(c, sql) == nueva for _, c in CAMPUS))
        assert contar("central", "SELECT count(*) FROM public.layer_styles WHERE f_table_name = 'parqueos'") >= 2
    finally:
        generar_estilos.activar("parqueos", anterior)
    esperar_hasta(lambda: all(contar(c, sql) == anterior for _, c in CAMPUS))
    return f"v{nueva} llegó a los 5 campus en {segundos} s y se volvió a v{anterior}"


def prueba_estilos_solo_lectura_en_campus():
    """En un campus no se puede modificar layer_styles (se administra en el central)"""
    conexion = conectar("cartago")
    try:
        conexion.cursor().execute("UPDATE public.layer_styles SET description = 'x'")
        raise AssertionError("se pudo modificar layer_styles en un campus")
    except psycopg2.Error as error:
        assert "nodo central" in error.diag.message_primary
    finally:
        conexion.close()


PRUEBAS = [
    prueba_login_correcto_por_campus,
    prueba_login_incorrecto,
    prueba_login_inactivo,
    prueba_claves_con_hash,
    prueba_rol_login_restringido,
    prueba_datos_nodo_sirven,
    prueba_estilos_en_todos_los_nodos,
    prueba_qml_valido,
    prueba_version_nueva_y_volver,
    prueba_estilos_solo_lectura_en_campus,
]
