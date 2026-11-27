"""
Escenarios de falla y recuperación de SIG-TEC (para la demostración y las pruebas).

  A  "Borrado por error en San Carlos"
     1. Respaldo físico de San Carlos.
     2. Se crea un edificio nuevo DESPUÉS del respaldo (para mostrar que el WAL lo recupera).
     3. Se anota la hora T.
     4. Error: se borran todos los puntos de interés y luminarias de San Carlos.
        El borrado se replica al central y a los otros campus (la replicación copia también los errores).
     5. PITR de San Carlos hasta T + resincronización.
     6. Se comprueba: puntos y luminarias de vuelta, el edificio nuevo sigue, todo consistente.

  B  "Se pierde el nodo de Limón completo"
     1. Respaldo físico de Limón (modo fisico).
     2. Se crea un punto de interés nuevo en Limón y se archiva el WAL.
     3. Se borra el contenedor y el volumen de datos de Limón.
     4. Recuperación:
          fisico         -> último respaldo físico + todo el WAL archivado
          desde_central  -> nodo nuevo, datos rescatados de la copia del central
     5. Se comprueba: el punto nuevo está, todo consistente, se puede editar otra vez.

Uso:
    python scripts/escenarios.py a
    python scripts/escenarios.py b fisico
    python scripts/escenarios.py b desde_central
"""
import sys
import time

import restaurar
import verificar_consistencia
from comun import SRID, conectar, contar, esperar_hasta
from respaldos import forzar_archivo_wal, respaldo_fisico
from simular_falla import perder_nodo


def ejecutar(nodo, sql, parametros=None):
    """Ejecuta una sentencia SQL en el nodo indicado."""
    conexion = conectar(nodo)
    conexion.cursor().execute(sql, parametros)
    conexion.close()


def consistente():
    """Devuelve las capas que NO son iguales en los 6 nodos. Vacía si todo coincide."""
    diferentes = [f"{e}.{c}" for e, c, _, ok in verificar_consistencia.comparar() if not ok]
    return diferentes


def titulo(texto):
    """Imprime el título de un paso del escenario."""
    print(f"\n=== {texto} ===")


# ---------------------------------------------------------------------
def escenario_a():
    """Escenario A: borrado por error en San Carlos y recuperación a un instante (PITR).
    Devuelve (resultado de cada comprobación, capas diferentes, tiempos)."""
    nodo = "san_carlos"
    tiempos = {}
    # Consultas que se repiten para comparar antes y después
    contar_puntos = f"SELECT count(*) FROM {nodo}.puntos_interes"
    contar_luces = f"SELECT count(*) FROM {nodo}.iluminacion"

    titulo("A.1 Respaldo físico de San Carlos")
    respaldo_fisico(nodo)

    titulo("A.2 Cambio DESPUÉS del respaldo (lo debe recuperar el WAL)")
    nombre_nuevo = f"Edificio posterior al respaldo {int(time.time())}"
    ejecutar(nodo, f"INSERT INTO {nodo}.edificios (nombre, area, pisos, geom) VALUES (%s, 100, 1, "
                   f"ST_MakeEnvelope(444100, 1145700, 444110, 1145710, {SRID}))", (nombre_nuevo,))
    print(f"  insertado: {nombre_nuevo}")
    # Cantidades que debe haber al final, después de recuperar
    puntos, luces = contar(nodo, contar_puntos), contar(nodo, contar_luces)
    # T es el instante al que se va a volver. Las pausas lo separan del INSERT y del borrado
    time.sleep(2)
    hora_t = contar(nodo, "SELECT now()::timestamptz(0)::text")
    print(f"  T = {hora_t}   (puntos de interés={puntos}, luminarias={luces})")
    time.sleep(2)

    titulo("A.3 ERROR: alguien borra todos los puntos de interés y luminarias de San Carlos")
    ejecutar(nodo, f"DELETE FROM {nodo}.puntos_interes")
    ejecutar(nodo, f"DELETE FROM {nodo}.iluminacion")
    # Se espera a que el borrado llegue a Cartago, para mostrar que la replicación no lo evita
    esperar_hasta(lambda: contar("cartago", contar_puntos) == 0)
    print(f"  San Carlos: {contar(nodo, contar_puntos)} puntos | central: {contar('central', contar_puntos)} "
          f"| Cartago: {contar('cartago', contar_puntos)}   <- el borrado ya se replicó")

    titulo(f"A.4 PITR de San Carlos hasta T = {hora_t}")
    tiempos["restaurar"], tiempos["resincronizar"] = restaurar.pitr(nodo, hora_t)

    titulo("A.5 Comprobación")
    # Cada valor es (obtenido, esperado). La prueba pasa si todos coinciden
    resultado = {
        "puntos": (contar(nodo, contar_puntos), puntos),
        "luminarias": (contar(nodo, contar_luces), luces),
        "puntos_en_cartago": (contar("cartago", contar_puntos), puntos),
        "edificio_posterior": (contar(nodo, f"SELECT count(*) FROM {nodo}.edificios WHERE nombre = %s",
                                      (nombre_nuevo,)), 1),
    }
    for clave, (obtenido, esperado) in resultado.items():
        print(f"  {clave:<20} {obtenido} (esperado {esperado}) {'OK' if obtenido == esperado else 'MAL'}")
    # Al final los 6 nodos deben tener las mismas 40 capas
    diferentes = consistente()
    print(f"  consistencia: {'40 capas OK' if not diferentes else 'DIFERENTES ' + str(diferentes)}")
    print(f"  tiempos: restaurar+WAL {tiempos['restaurar']:.0f} s, resincronizar {tiempos['resincronizar']:.0f} s")
    return resultado, diferentes, tiempos


# ---------------------------------------------------------------------
def escenario_b(modo):
    """Escenario B: se pierde el nodo de Limón. Se recupera con el respaldo físico (modo 'fisico')
    o desde la copia del central (modo 'desde_central').
    Devuelve (resultado de cada comprobación, capas diferentes, tiempos)."""
    nodo = "limon"
    tiempos = {}
    # Solo el modo físico necesita un respaldo previo. El otro usa la copia del central
    if modo == "fisico":
        titulo("B.1 Respaldo físico de Limón")
        respaldo_fisico(nodo)

    titulo("B.2 Cambio reciente en Limón")
    nombre_nuevo = f"Punto antes de la falla {int(time.time())}"
    ejecutar(nodo, f"INSERT INTO {nodo}.puntos_interes (nombre, tipo, geom) VALUES (%s, 'soda', "
                   f"ST_SetSRID(ST_MakePoint(589000, 1105000), {SRID}))", (nombre_nuevo,))
    esperar_hasta(lambda: contar("central", f"SELECT count(*) FROM {nodo}.puntos_interes WHERE nombre = %s",
                                 (nombre_nuevo,)) == 1)
    print(f"  insertado y replicado al central: {nombre_nuevo}")
    # Se cierra el WAL actual para que el cambio quede en el archivo de WAL
    print(f"  WAL archivado hasta {forzar_archivo_wal(nodo)}")
    # Cantidad de puntos que debe tener Limón después de recuperarse
    total = contar(nodo, f"SELECT count(*) FROM {nodo}.puntos_interes")

    titulo("B.3 FALLA: se pierde el nodo de Limón (contenedor y volumen de datos)")
    # El tiempo total se mide desde que se pierde el nodo
    inicio = time.time()
    perder_nodo(nodo)

    titulo(f"B.4 Recuperación ({modo})")
    if modo == "fisico":
        tiempos["restaurar"], tiempos["resincronizar"] = restaurar.fisico(nodo)
    else:
        tiempos["restaurar"], tiempos["resincronizar"] = restaurar.desde_central(nodo)
    tiempos["total"] = time.time() - inicio

    titulo("B.5 Comprobación")
    # Cada valor es (obtenido, esperado). La prueba pasa si todos coinciden
    resultado = {
        "punto_reciente": (contar(nodo, f"SELECT count(*) FROM {nodo}.puntos_interes WHERE nombre = %s",
                                  (nombre_nuevo,)), 1),
        "puntos_limon": (contar(nodo, f"SELECT count(*) FROM {nodo}.puntos_interes"), total),
        "vista_con_5_campus": (contar(nodo, "SELECT count(DISTINCT campus_id) FROM sig.edificios"), 5),
    }
    # Se puede seguir editando: un INSERT nuevo llega a Cartago
    otro = f"Punto después de recuperar {int(time.time())}"
    ejecutar(nodo, f"INSERT INTO sig.puntos_interes (nombre, tipo, geom) VALUES (%s, 'cajero', "
                   f"ST_SetSRID(ST_MakePoint(589010, 1105010), {SRID}))", (otro,))
    esperar_hasta(lambda: contar("cartago", "SELECT count(*) FROM sig.puntos_interes WHERE nombre = %s",
                                 (otro,)) == 1)
    resultado["edicion_despues"] = (1, 1)
    # Se borran los dos puntos de prueba y se espera a que el borrado también se replique
    ejecutar(nodo, f"DELETE FROM {nodo}.puntos_interes WHERE nombre IN (%s, %s)", (nombre_nuevo, otro))
    esperar_hasta(lambda: contar("cartago", "SELECT count(*) FROM sig.puntos_interes WHERE nombre = %s",
                                 (otro,)) == 0)

    for clave, (obtenido, esperado) in resultado.items():
        print(f"  {clave:<20} {obtenido} (esperado {esperado}) {'OK' if obtenido == esperado else 'MAL'}")
    # Al final los 6 nodos deben tener las mismas 40 capas
    diferentes = consistente()
    print(f"  consistencia: {'40 capas OK' if not diferentes else 'DIFERENTES ' + str(diferentes)}")
    print(f"  tiempos: restaurar {tiempos['restaurar']:.0f} s, resincronizar {tiempos['resincronizar']:.0f} s, "
          f"total desde la falla {tiempos['total']:.0f} s")
    return resultado, diferentes, tiempos


if __name__ == "__main__":
    escenario = sys.argv[1] if len(sys.argv) > 1 else ""
    if escenario == "a":
        escenario_a()
    elif escenario == "b":
        escenario_b(sys.argv[2] if len(sys.argv) > 2 else "fisico")
    else:
        sys.exit(__doc__)
