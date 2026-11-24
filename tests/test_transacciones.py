"""
Pruebas de la fase 3: transacciones distribuidas (2PC y modo síncrono).
La demo completa con el central caído está en scripts/modo_sincrono.py demo
(no se corre aquí porque apaga el central).
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import demo_2pc  # noqa: E402
import modo_sincrono  # noqa: E402
from comun import SRID, conectar, contar, esperar_hasta  # noqa: E402

CAMPUS = demo_2pc.CAMPUS_DEMO


def prueba_2pc_exito():
    """2PC: éxito -> el usuario (central) y su punto (campus) quedan en los dos nodos"""
    usuario = f"t2pc_{uuid.uuid4().hex[:6]}"
    try:
        assert demo_2pc.registrar_usuario_2pc(usuario) is True
        assert demo_2pc.existe_en_ambos(usuario) == (1, 1)
    finally:
        demo_2pc.limpiar([usuario])


def prueba_2pc_falla():
    """2PC: falla en el campus -> no queda nada en ninguno de los dos nodos"""
    usuario = f"t2pc_{uuid.uuid4().hex[:6]}"
    try:
        assert demo_2pc.registrar_usuario_2pc(usuario, tipo="tipo_invalido") is False
        assert demo_2pc.existe_en_ambos(usuario) == (0, 0)
        assert demo_2pc.preparadas("central") == [] and demo_2pc.preparadas(CAMPUS) == []
    finally:
        demo_2pc.limpiar([usuario])


def prueba_preparada_no_se_replica():
    """Una transacción PREPARADA no se replica hasta el COMMIT PREPARED"""
    nombre = f"PRUEBA-{uuid.uuid4().hex[:8]}"
    conexion = conectar(CAMPUS, autocommit=False)
    conexion.tpc_begin(nombre)
    conexion.cursor().execute(
        f"INSERT INTO {CAMPUS}.puntos_interes (nombre, tipo, geom) "
        f"VALUES (%s, 'otro', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID}))", (nombre,))
    conexion.tpc_prepare()
    conexion.close()

    # Marcador confirmado después: cuando llega al central, la preparada tampoco debe estar
    marcador = f"PRUEBA-{uuid.uuid4().hex[:8]}"
    c = conectar(CAMPUS)
    c.cursor().execute(f"INSERT INTO {CAMPUS}.puntos_interes (nombre, tipo, geom) "
                       f"VALUES (%s, 'otro', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID}))", (marcador,))
    c.close()
    sql = f"SELECT count(*) FROM {CAMPUS}.puntos_interes WHERE nombre = %s"
    esperar_hasta(lambda: contar("central", sql, (marcador,)) == 1)
    assert contar("central", sql, (nombre,)) == 0, "la transacción preparada llegó antes del COMMIT"

    # COMMIT PREPARED -> ahora sí llega
    c = conectar(CAMPUS)
    c.cursor().execute(f"COMMIT PREPARED '{nombre}'")
    c.cursor().execute(f"DELETE FROM {CAMPUS}.puntos_interes WHERE nombre IN (%s, %s)", (nombre, marcador))
    c.close()


def prueba_modo_sincrono():
    """Modo síncrono: el central queda como 'sync' y el COMMIT sigue funcionando"""
    try:
        modo_sincrono.activar(CAMPUS)
        sql = "SELECT sync_state FROM pg_stat_replication WHERE application_name = %s"
        esperar_hasta(lambda: contar(CAMPUS, sql, (f"sub_nivel1_{CAMPUS}",)) == "sync")
        ms = modo_sincrono.medir_commits(10)
    finally:
        modo_sincrono.desactivar(CAMPUS)
        c = conectar(CAMPUS)
        c.cursor().execute(f"DELETE FROM {CAMPUS}.puntos_interes WHERE nombre = 'DEMO-SYNC'")
        c.close()
    assert contar(CAMPUS, sql, (f"sub_nivel1_{CAMPUS}",)) == "async", "no volvió a asíncrono"
    return f"COMMIT síncrono promedio {ms} ms"


PRUEBAS = [
    prueba_2pc_exito,
    prueba_2pc_falla,
    prueba_preparada_no_se_replica,
    prueba_modo_sincrono,
]
