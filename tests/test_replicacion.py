"""
Pruebas de la fase 3: replicación lógica en dos niveles y atomicidad.

Todas las filas de prueba llevan un nombre que empieza con 'PRUEBA-' y se borran al final.
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from comun import CAMPUS, NODOS, SRID, conectar, contar, esperar_hasta  # noqa: E402

ORIGEN = "san_carlos"                       # campus donde se edita en las pruebas
OTROS = [n for n in NODOS if n != ORIGEN]   # central + los otros 4 campus


def etiqueta():
    """Nombre único para las filas de prueba (PRUEBA-xxxxxxxx)."""
    return f"PRUEBA-{uuid.uuid4().hex[:8]}"


def punto_sql(x=495000, y=1145000):
    """Geometría de un punto en el SRID institucional, para las pruebas."""
    return f"ST_SetSRID(ST_MakePoint({x}, {y}), {SRID})"


def cuantos(nodo, tabla, columna, valor):
    """Cuenta las filas del esquema de San Carlos que tienen ese valor en la columna."""
    return contar(nodo, f"SELECT count(*) FROM {ORIGEN}.{tabla} WHERE {columna} = %s", (valor,))


def en_todos(tabla, columna, valor, esperado):
    """True si los 5 nodos que reciben copia tienen 'esperado' filas con ese valor."""
    return all(cuantos(n, tabla, columna, valor) == esperado for n in OTROS)


def ejecutar(nodo, sql, parametros=None):
    """Ejecuta una sentencia SQL en el nodo indicado."""
    conexion = conectar(nodo)
    conexion.cursor().execute(sql, parametros)
    conexion.close()


# ---------------------------------------------------------------------
def prueba_insert_dos_niveles():
    """Nivel 1 y 2: un INSERT en San Carlos llega al central y a los otros 4 campus"""
    nombre = etiqueta()
    ejecutar(ORIGEN, f"INSERT INTO {ORIGEN}.puntos_interes (nombre, tipo, geom) VALUES (%s, 'otro', {punto_sql()})", (nombre,))
    t_central = esperar_hasta(lambda: cuantos("central", "puntos_interes", "nombre", nombre) == 1)
    t_todos = esperar_hasta(lambda: en_todos("puntos_interes", "nombre", nombre, 1))
    # Sin vuelta: el campus de origen sigue con una sola copia (sin duplicados ni errores)
    assert cuantos(ORIGEN, "puntos_interes", "nombre", nombre) == 1
    ejecutar(ORIGEN, f"DELETE FROM {ORIGEN}.puntos_interes WHERE nombre = %s", (nombre,))
    return f"central {t_central} s, los 5 nodos {t_todos} s"


def prueba_update_delete():
    """UPDATE y DELETE también se replican (REPLICA IDENTITY = clave primaria)"""
    nombre = etiqueta()
    ejecutar(ORIGEN, f"INSERT INTO {ORIGEN}.puntos_interes (nombre, tipo, geom) VALUES (%s, 'otro', {punto_sql()})", (nombre,))
    esperar_hasta(lambda: en_todos("puntos_interes", "nombre", nombre, 1))

    ejecutar(ORIGEN, f"UPDATE {ORIGEN}.puntos_interes SET descripcion = 'editado', "
                     f"geom = ST_Translate(geom, 10, 10) WHERE nombre = %s", (nombre,))
    esperar_hasta(lambda: all(
        contar(n, f"SELECT count(*) FROM {ORIGEN}.puntos_interes WHERE nombre = %s "
                  f"AND descripcion = 'editado' AND ST_X(geom) = 495010", (nombre,)) == 1
        for n in OTROS))

    ejecutar(ORIGEN, f"DELETE FROM {ORIGEN}.puntos_interes WHERE nombre = %s", (nombre,))
    esperar_hasta(lambda: en_todos("puntos_interes", "nombre", nombre, 0))


def prueba_transaccion_atomica():
    """Una transacción de varias filas (edificio + 4 luminarias) llega completa o no llega"""
    nombre = etiqueta()
    conexion = conectar(ORIGEN, autocommit=False)
    cursor = conexion.cursor()
    cursor.execute(f"""INSERT INTO {ORIGEN}.edificios (nombre, codigo, area, pisos, geom)
                       VALUES (%s, %s, 100, 1, ST_MakeEnvelope(495000, 1145000, 495010, 1145010, {SRID}))""",
                   (nombre, nombre))
    for i in range(4):
        cursor.execute(f"INSERT INTO {ORIGEN}.iluminacion (codigo, potencia, estado, geom) "
                       f"VALUES (%s, 100, 'funcionando', {punto_sql(495000 + i, 1145000)})", (nombre,))
    conexion.commit()
    conexion.close()

    # Mientras llega, en el central solo se puede ver "nada" (0+0) o "todo" (1+4), nunca a medias
    vistos = set()
    def completo():
        """Lee en el central (edificio x 10 + luminarias) y lo guarda, para ver si alguna vez hubo un estado a medias."""
        valor = contar("central", f"""
            SELECT (SELECT count(*) FROM {ORIGEN}.edificios WHERE nombre = %s) * 10
                 + (SELECT count(*) FROM {ORIGEN}.iluminacion WHERE codigo = %s)""", (nombre, nombre))
        vistos.add(valor)
        return valor == 14
    esperar_hasta(completo)
    assert vistos <= {0, 14}, f"se vio un estado a medias: {vistos}"
    esperar_hasta(lambda: en_todos("iluminacion", "codigo", nombre, 4) and en_todos("edificios", "nombre", nombre, 1))

    # Limpiar (también en una sola transacción)
    conexion = conectar(ORIGEN, autocommit=False)
    conexion.cursor().execute(f"DELETE FROM {ORIGEN}.iluminacion WHERE codigo = %s", (nombre,))
    conexion.cursor().execute(f"DELETE FROM {ORIGEN}.edificios WHERE nombre = %s", (nombre,))
    conexion.commit()
    conexion.close()
    esperar_hasta(lambda: en_todos("iluminacion", "codigo", nombre, 0))
    return f"estados vistos en el central: {sorted(vistos)}"


def prueba_rollback_no_replica():
    """Un ROLLBACK no se replica a ningún nodo"""
    nombre = etiqueta()
    conexion = conectar(ORIGEN, autocommit=False)
    conexion.cursor().execute(f"INSERT INTO {ORIGEN}.puntos_interes (nombre, tipo, geom) VALUES (%s, 'otro', {punto_sql()})", (nombre,))
    conexion.rollback()
    conexion.close()
    # Marcador: una fila confirmada DESPUÉS del rollback. Cuando el marcador llega,
    # sabemos que la replicación ya pasó por el punto del rollback.
    marcador = etiqueta()
    ejecutar(ORIGEN, f"INSERT INTO {ORIGEN}.puntos_interes (nombre, tipo, geom) VALUES (%s, 'otro', {punto_sql()})", (marcador,))
    esperar_hasta(lambda: en_todos("puntos_interes", "nombre", marcador, 1))
    for nodo in NODOS:
        assert cuantos(nodo, "puntos_interes", "nombre", nombre) == 0, f"el rollback apareció en {nodo}"
    ejecutar(ORIGEN, f"DELETE FROM {ORIGEN}.puntos_interes WHERE nombre = %s", (marcador,))


def prueba_suscripciones_activas():
    """Las 10 suscripciones están activas y con su proceso de aplicación corriendo"""
    # Nota: no se usa apply_error_count porque también cuenta las veces que el publicador
    # estuvo caído (por ejemplo en la demo del modo síncrono) y nunca vuelve a cero.
    total = 0
    for nodo in NODOS:
        total += contar(nodo, """SELECT count(*) FROM pg_subscription s
                                 JOIN pg_stat_subscription w ON w.subid = s.oid AND w.relid IS NULL
                                 WHERE s.subenabled AND w.pid IS NOT NULL""")
    assert total == 10, f"solo {total} de 10 suscripciones con proceso activo"
    return "10 suscripciones"


def prueba_consistencia():
    """verificar_consistencia: las 40 capas son iguales en los 6 nodos"""
    import verificar_consistencia
    time.sleep(1)
    diferentes = [f"{e}.{c}" for e, c, _, ok in verificar_consistencia.comparar() if not ok]
    assert not diferentes, f"diferentes: {diferentes}"
    return "40 capas OK"


PRUEBAS = [
    prueba_insert_dos_niveles,
    prueba_update_delete,
    prueba_transaccion_atomica,
    prueba_rollback_no_replica,
    prueba_suscripciones_activas,
    prueba_consistencia,
]
