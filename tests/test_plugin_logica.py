"""
Pruebas de la lógica del plugin (plugin/sigtec/logica.py) con Python normal, sin QGIS.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "plugin"))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
from sigtec import logica  # noqa: E402  (logica.py no importa nada de QGIS)
from comun import ENV, NODOS  # noqa: E402


def ejecutor_central():
    """Ejecutor de SQL hacia el nodo central con los datos de config.ini."""
    c = logica.leer_config()["central"]
    return logica.ejecutor_psycopg2(c["host"], c["puerto"], c["base"], c["usuario"], c["clave"])


def prueba_config():
    """config.ini apunta al central del .env y al SRID institucional"""
    config = logica.leer_config()
    assert config["central"]["puerto"] == NODOS["central"]["puerto"]
    assert config["central"]["usuario"] == ENV["LOGIN_USER"]
    assert config["srid"] == int(ENV["SRID"])


def prueba_autenticar_ok():
    """autenticar() del plugin devuelve el campus y el nodo de San Carlos"""
    datos = logica.autenticar(ejecutor_central(), "sancarlos1", "tec2026")
    assert datos["campus_id"] == 3 and datos["puerto"] == NODOS["san_carlos"]["puerto"]
    return f"{datos['usuario']} -> {datos['campus_nombre']} ({datos['host']}:{datos['puerto']})"


def prueba_autenticar_mal():
    """Clave mala, campos vacíos o servidor caído dan ErrorSigTec con mensaje en español"""
    casos = [(ejecutor_central(), "sancarlos1", "mala", "incorrectos"),
             (ejecutor_central(), "", "", "Escriba"),
             (logica.ejecutor_psycopg2("127.0.0.1", 1, "x", "x", "x"), "a", "b", "No se pudo conectar")]
    for ejecutar, usuario, clave, esperado in casos:
        try:
            logica.autenticar(ejecutar, usuario, clave)
            raise AssertionError(f"no falló: {usuario}")
        except logica.ErrorSigTec as error:
            assert esperado in str(error), str(error)


def prueba_estilos_y_extension():
    """Con los datos del nodo se leen los 8 estilos vigentes y la zona del campus"""
    datos = logica.autenticar(ejecutor_central(), "sancarlos1", "tec2026")
    ejecutar = logica.ejecutor_psycopg2("127.0.0.1", datos["puerto"], datos["base"],
                                        datos["usuario_conexion"], datos["clave_conexion"])
    estilos = logica.estilos_vigentes(ejecutar)
    assert set(estilos) == {vista for vista, _, _ in logica.CAPAS}, set(estilos)
    xmin, ymin, xmax, ymax = logica.extension_campus(ejecutar, 3)
    assert xmax - xmin < 2000 and ymax - ymin < 2000, "la zona del campus es demasiado grande"
    return f"8 estilos, zona de {round(xmax - xmin)} x {round(ymax - ymin)} m"


def prueba_limpiar_error():
    """limpiar_error saca solo el mensaje del trigger del texto que muestra QGIS"""
    texto = ("PostGIS error while changing attributes: ERROR:  No puede modificar el objeto 1000001 "
             "porque pertenece al Campus Tecnológico Central Cartago.\nCONTEXT:  PL/pgSQL function ...")
    assert logica.limpiar_error(texto) == ("No puede modificar el objeto 1000001 porque pertenece "
                                           "al Campus Tecnológico Central Cartago.")
    assert logica.limpiar_error("otro texto") == "otro texto"


def prueba_armar_sql():
    """armar_sql (para el ejecutor de QGIS) escapa las comillas: no hay inyección SQL"""
    sql = logica.armar_sql("SELECT * FROM public.autenticar(%s, %s)", ("x' OR '1'='1", "a"))
    assert sql == "SELECT * FROM public.autenticar('x'' OR ''1''=''1', 'a')", sql
    # Y la base lo trata como un texto cualquiera (login fallido, no un error de SQL)
    try:
        logica.autenticar(ejecutor_central(), "x' OR '1'='1", "a")
        raise AssertionError("entró con inyección")
    except logica.ErrorSigTec as error:
        assert "incorrectos" in str(error)


PRUEBAS = [
    prueba_config,
    prueba_autenticar_ok,
    prueba_autenticar_mal,
    prueba_estilos_y_extension,
    prueba_limpiar_error,
    prueba_armar_sql,
]
