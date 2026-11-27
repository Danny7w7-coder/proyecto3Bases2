"""
Lógica del plugin SIG-TEC, SIN nada de QGIS.
Así se puede probar con Python normal (tests/test_plugin_logica.py).

Para hablar con la base se usa un "ejecutor": una función ejecutar(sql, parametros)
que devuelve una lista de diccionarios. Hay dos:
    - ejecutor_psycopg2(): usa psycopg2 (viene incluido en QGIS para Windows)
    - conexion_qgis.ejecutor_qgis(): usa la conexión propia de QGIS (por si no hay psycopg2)
"""
import configparser
import os
import re

# Las 8 capas: (vista en el esquema sig, nombre para mostrar, tipo de geometría)
# Están en el orden en que se dibujan: primero (arriba) los puntos, al final (abajo) los polígonos.
CAPAS = [
    ("puntos_interes", "Puntos de interés", "Point"),
    ("iluminacion",    "Iluminación",       "Point"),
    ("accesibilidad",  "Accesibilidad",     "LineString"),
    ("aceras",         "Aceras",            "LineString"),
    ("carreteras",     "Carreteras",        "LineString"),
    ("edificios",      "Edificios",         "Polygon"),
    ("parqueos",       "Parqueos",          "Polygon"),
    ("zonas_verdes",   "Zonas verdes",      "Polygon"),
]

ESQUEMA_VISTAS = "sig"
COLUMNA_GEOMETRIA = "geom"
COLUMNA_CLAVE = "id"


class ErrorSigTec(Exception):
    """Error con un mensaje en español listo para mostrar al usuario."""


# ---------------------------------------------------------------------
# Configuración (config.ini junto al plugin)
# ---------------------------------------------------------------------
def leer_config(ruta=None):
    """Lee config.ini y devuelve los datos de conexión al nodo central y el SRID."""
    ruta = ruta or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
    config = configparser.ConfigParser()
    if not config.read(ruta, encoding="utf-8"):
        raise ErrorSigTec(f"No se encontró el archivo de configuración: {ruta}")
    central = config["central"]
    return {
        "central": {
            "host": central.get("host", "localhost"),
            "puerto": central.getint("puerto", 5440),
            "base": central.get("base", "sigtec"),
            "usuario": central.get("usuario", "sigtec_login"),
            "clave": central.get("clave", ""),
        },
        "srid": config.getint("sistema", "srid", fallback=5367),
    }


# ---------------------------------------------------------------------
# Ejecutor con psycopg2
# ---------------------------------------------------------------------
def psycopg2_disponible():
    """Devuelve True si el Python de QGIS tiene psycopg2 instalado."""
    try:
        import psycopg2  # noqa: F401
        return True
    except ImportError:
        return False


def ejecutor_psycopg2(host, puerto, base, usuario, clave):
    """Devuelve una función ejecutar(sql, parametros) que usa psycopg2."""
    import psycopg2

    def ejecutar(sql, parametros=()):
        """Abre una conexión, ejecuta la consulta y devuelve las filas como diccionarios. Los errores se convierten en ErrorSigTec con un mensaje en español."""
        try:
            conexion = psycopg2.connect(host=host, port=puerto, dbname=base, user=usuario,
                                        password=clave, connect_timeout=5)
        except psycopg2.OperationalError as error:
            raise ErrorSigTec(f"No se pudo conectar a {host}:{puerto}. ¿Está encendido el servidor?\n{error}")
        try:
            cursor = conexion.cursor()
            cursor.execute(sql, parametros)
            columnas = [c.name for c in cursor.description] if cursor.description else []
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()] if columnas else []
            conexion.commit()
            return filas
        except psycopg2.Error as error:
            raise ErrorSigTec(error.diag.message_primary or str(error))
        finally:
            conexion.close()

    return ejecutar


# ---------------------------------------------------------------------
# Operaciones del plugin
# ---------------------------------------------------------------------
def autenticar(ejecutar, usuario, clave):
    """Llama a public.autenticar() en el central. Devuelve los datos del usuario y su nodo."""
    if not usuario or not clave:
        raise ErrorSigTec("Escriba el usuario y la contraseña.")
    filas = ejecutar("SELECT * FROM public.autenticar(%s, %s)", (usuario, clave))
    if not filas:
        raise ErrorSigTec("Usuario o contraseña incorrectos.")
    datos = filas[0]
    # El puerto puede venir como texto si se usa el ejecutor de QGIS
    datos["puerto"] = int(datos["puerto"])
    datos["campus_id"] = int(datos["campus_id"])
    return datos


def estilos_vigentes(ejecutar):
    """Devuelve {capa: qml} con el estilo vigente de cada vista (tabla layer_styles del nodo)."""
    filas = ejecutar("SELECT f_table_name, styleqml::text AS qml FROM public.layer_styles "
                     "WHERE f_table_schema = %s AND vigente", (ESQUEMA_VISTAS,))
    return {fila["f_table_name"]: fila["qml"] for fila in filas}


def extension_campus(ejecutar, campus_id):
    """Rectángulo (xmin, ymin, xmax, ymax) que cubre los edificios y calles del campus."""
    filas = ejecutar(
        "SELECT ST_XMin(e) AS xmin, ST_YMin(e) AS ymin, ST_XMax(e) AS xmax, ST_YMax(e) AS ymax "
        "FROM (SELECT ST_Extent(geom) AS e FROM (SELECT geom FROM sig.edificios WHERE campus_id = %s "
        "      UNION ALL SELECT geom FROM sig.carreteras WHERE campus_id = %s) t) x",
        (campus_id, campus_id))
    fila = filas[0] if filas else None
    if not fila or fila["xmin"] is None:
        return None
    return tuple(float(fila[k]) for k in ("xmin", "ymin", "xmax", "ymax"))


# ---------------------------------------------------------------------
# Mensajes de error
# ---------------------------------------------------------------------
def limpiar_error(texto):
    """Saca el mensaje útil de un error de PostgreSQL/QGIS.

    QGIS muestra algo como:
      'PostGIS error while changing attributes: ERROR:  No puede modificar el objeto ...
       CONTEXT:  PL/pgSQL function ...'
    y aquí se devuelve solo: 'No puede modificar el objeto ...'
    """
    if not texto:
        return ""
    coincidencia = re.search(r"ERROR:\s+(.+?)(?:\n|\s+CONTEXT:|\s+DETAIL:|$)", texto, re.DOTALL)
    mensaje = coincidencia.group(1) if coincidencia else texto
    return mensaje.strip()


def literal_sql(valor):
    """Convierte un valor de Python en un literal SQL seguro (para el ejecutor de QGIS,
    que no acepta parámetros). Las comillas simples se duplican."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def armar_sql(sql, parametros):
    """Reemplaza cada %s del SQL por el literal del parámetro correspondiente."""
    partes = sql.split("%s")
    if len(partes) - 1 != len(parametros):
        raise ValueError("la cantidad de %s no coincide con los parámetros")
    resultado = partes[0]
    for valor, resto in zip(parametros, partes[1:]):
        resultado += literal_sql(valor) + resto
    return resultado
