"""
Pruebas de la fase 4: vistas distribuidas sig.* y triggers INSTEAD OF.
Se conectan con el rol del campus (sigtec_san_carlos), igual que lo hará QGIS.
"""
import os
import sys
import uuid

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from cargar_datos import CAPAS  # noqa: E402
from comun import CAMPUS, ENV, SRID, conectar, contar, esperar_hasta  # noqa: E402

NODO = "san_carlos"          # nodo donde trabaja el usuario de la prueba
ROL = f"sigtec_{NODO}"
AJENO = "cartago"            # otro campus


def conectar_rol(autocommit=True):
    return conectar(NODO, autocommit, usuario=ROL, clave=ENV["EDITOR_PASSWORD"])


def ejecutar_rol(sql, parametros=None):
    """Ejecuta como el rol del campus. Devuelve (filas, None) o (None, mensaje de error)."""
    conexion = conectar_rol()
    cursor = conexion.cursor()
    try:
        cursor.execute(sql, parametros)
        filas = cursor.fetchall() if cursor.description else []
        return filas, None
    except psycopg2.Error as error:
        return None, error.diag.message_primary
    finally:
        conexion.close()


def etiqueta():
    return f"PRUEBA-{uuid.uuid4().hex[:8]}"


def borrar(nombre):
    conexion = conectar(NODO)
    conexion.cursor().execute(f"DELETE FROM {NODO}.puntos_interes WHERE nombre = %s", (nombre,))
    conexion.close()


# ---------------------------------------------------------------------
def prueba_vistas_juntan_campus():
    """Cada vista sig.<capa> muestra los objetos de los 5 campus"""
    for capa in CAPAS:
        en_vista = contar(NODO, f"SELECT count(*) FROM sig.{capa}")
        en_tablas = sum(contar(NODO, f"SELECT count(*) FROM {e}.{capa}") for _, e in CAMPUS)
        campus_distintos = contar(NODO, f"SELECT count(DISTINCT campus_id) FROM sig.{capa}")
        assert en_vista == en_tablas and campus_distintos == 5, f"sig.{capa}: {en_vista} filas, {campus_distintos} campus"
    return "8 vistas con los 5 campus"


def prueba_insert_propio():
    """INSERT en la vista: va a la tabla del campus, con su campus_id e id de su rango"""
    nombre = etiqueta()
    # Se manda campus_id = 1 a propósito: el trigger debe forzarlo a 3 (San Carlos)
    filas, error = ejecutar_rol(
        f"INSERT INTO sig.puntos_interes (campus_id, nombre, tipo, geom) "
        f"VALUES (1, %s, 'soda', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID})) RETURNING id, campus_id",
        (nombre,))
    try:
        assert error is None, error
        nuevo_id, campus_id = filas[0]
        assert campus_id == 3 and 3_000_000 < nuevo_id < 4_000_000, f"id={nuevo_id} campus={campus_id}"
        assert contar(NODO, f"SELECT count(*) FROM {NODO}.puntos_interes WHERE id = %s", (nuevo_id,)) == 1
        return f"id {nuevo_id}, campus_id forzado a 3"
    finally:
        borrar(nombre)


def prueba_insert_otro_srid():
    """INSERT con geometría en EPSG:4326: se guarda transformada al SRID institucional"""
    nombre = etiqueta()
    # Punto en lat/lon cerca del campus San Carlos
    filas, error = ejecutar_rol(
        "INSERT INTO sig.puntos_interes (nombre, tipo, geom) "
        "VALUES (%s, 'cajero', ST_SetSRID(ST_MakePoint(-84.5116, 10.3606), 4326)) RETURNING id", (nombre,))
    try:
        assert error is None, error
        srid, x = conectar_y_leer(f"SELECT ST_SRID(geom), round(ST_X(geom)) FROM {NODO}.puntos_interes WHERE id = %s",
                                  (filas[0][0],))
        assert srid == SRID, f"quedó en SRID {srid}"
        assert 400000 < x < 600000, f"X={x} no parece CRTM05"
        return f"4326 -> {srid} (X = {x})"
    finally:
        borrar(nombre)


def prueba_insert_multipoligono():
    """INSERT de un MultiPolygon de una parte (como lo manda QGIS): se guarda como Polygon"""
    nombre = etiqueta()
    filas, error = ejecutar_rol(
        f"INSERT INTO sig.edificios (nombre, area, pisos, geom) VALUES (%s, 100, 1, "
        f"ST_Multi(ST_MakeEnvelope(495000, 1145000, 495010, 1145010, {SRID}))) RETURNING id", (nombre,))
    try:
        assert error is None, error
        tipo = conectar_y_leer(f"SELECT GeometryType(geom) FROM {NODO}.edificios WHERE id = %s", (filas[0][0],))[0]
        assert tipo == "POLYGON", tipo
    finally:
        conexion = conectar(NODO)
        conexion.cursor().execute(f"DELETE FROM {NODO}.edificios WHERE nombre = %s", (nombre,))
        conexion.close()


def conectar_y_leer(sql, parametros):
    conexion = conectar(NODO)
    cursor = conexion.cursor()
    cursor.execute(sql, parametros)
    fila = cursor.fetchone()
    conexion.close()
    return fila


def prueba_update_delete_propio():
    """UPDATE y DELETE de un objeto propio funcionan a través de la vista"""
    nombre = etiqueta()
    filas, _ = ejecutar_rol(
        f"INSERT INTO sig.puntos_interes (nombre, tipo, geom) "
        f"VALUES (%s, 'soda', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID})) RETURNING id", (nombre,))
    nuevo_id = filas[0][0]
    _, error = ejecutar_rol("UPDATE sig.puntos_interes SET descripcion = 'editada', "
                            f"geom = ST_SetSRID(ST_MakePoint(495005, 1145005), {SRID}) WHERE id = %s", (nuevo_id,))
    assert error is None, error
    assert conectar_y_leer(f"SELECT descripcion FROM {NODO}.puntos_interes WHERE id = %s", (nuevo_id,))[0] == "editada"
    _, error = ejecutar_rol("DELETE FROM sig.puntos_interes WHERE id = %s", (nuevo_id,))
    assert error is None, error
    assert contar(NODO, f"SELECT count(*) FROM {NODO}.puntos_interes WHERE id = %s", (nuevo_id,)) == 0


def prueba_editar_ajeno_rechazado():
    """UPDATE o DELETE de un objeto de otro campus se rechaza con mensaje claro"""
    id_ajeno = contar(NODO, f"SELECT min(id) FROM {AJENO}.edificios")
    _, error_update = ejecutar_rol("UPDATE sig.edificios SET pisos = 9 WHERE id = %s", (id_ajeno,))
    _, error_delete = ejecutar_rol("DELETE FROM sig.edificios WHERE id = %s", (id_ajeno,))
    assert error_update and "pertenece al Campus Tecnológico Central Cartago" in error_update, error_update
    assert error_delete and "No puede eliminar" in error_delete, error_delete
    assert contar(NODO, f"SELECT pisos FROM {AJENO}.edificios WHERE id = %s", (id_ajeno,)) != 9
    return error_update


def prueba_cambiar_campus_rechazado():
    """No se puede cambiar el campus_id de un objeto propio"""
    id_propio = contar(NODO, f"SELECT min(id) FROM {NODO}.edificios")
    _, error = ejecutar_rol("UPDATE sig.edificios SET campus_id = 1 WHERE id = %s", (id_propio,))
    assert error and "No se puede cambiar el campus" in error, error


def prueba_tablas_solo_lectura_para_rol():
    """El rol del campus no puede escribir directo en las tablas (ni en las propias)"""
    for tabla in [f"{NODO}.edificios", f"{AJENO}.edificios"]:
        _, error = ejecutar_rol(f"DELETE FROM {tabla} WHERE id = 0")
        assert error and "permission denied" in error, f"{tabla}: {error}"
    filas, error = ejecutar_rol(f"SELECT count(*) FROM {AJENO}.edificios")
    assert error is None and filas[0][0] > 0, "no puede leer las réplicas"


def prueba_aparece_en_otro_campus():
    """Un objeto insertado en San Carlos aparece en la vista de Cartago tras un breve retraso"""
    nombre = etiqueta()
    ejecutar_rol(f"INSERT INTO sig.puntos_interes (nombre, tipo, geom) "
                 f"VALUES (%s, 'soda', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID}))", (nombre,))
    try:
        segundos = esperar_hasta(lambda: contar(AJENO, "SELECT count(*) FROM sig.puntos_interes WHERE nombre = %s",
                                                (nombre,)) == 1)
        return f"visible en Cartago en {segundos} s"
    finally:
        borrar(nombre)


PRUEBAS = [
    prueba_vistas_juntan_campus,
    prueba_insert_propio,
    prueba_insert_otro_srid,
    prueba_insert_multipoligono,
    prueba_update_delete_propio,
    prueba_editar_ajeno_rechazado,
    prueba_cambiar_campus_rechazado,
    prueba_tablas_solo_lectura_para_rol,
    prueba_aparece_en_otro_campus,
]
