"""
Pruebas de la fase 7: respaldos y recuperación.
OJO: los escenarios apagan, borran y restauran nodos de verdad (tardan alrededor de 1 minuto en total).
"""
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import escenarios  # noqa: E402
import respaldos  # noqa: E402
from comun import NODOS, contar  # noqa: E402


def revisar(resultado, diferentes):
    """Falla si algún valor no es el esperado o si hay capas diferentes entre nodos."""
    malos = {k: v for k, v in resultado.items() if v[0] != v[1]}
    assert not malos, f"valores distintos a lo esperado: {malos}"
    assert not diferentes, f"capas diferentes entre nodos: {diferentes}"


def prueba_respaldo_logico():
    """pg_dump de la base completa y del esquema propio en los 6 nodos, y el completo se puede restaurar"""
    for nodo in NODOS:
        completo, parcial = respaldos.respaldo_logico(nodo)
        assert os.path.getsize(completo) > 0 and os.path.getsize(parcial) > 0
    original, restaurado = respaldos.verificar_logico("cartago")
    assert original == restaurado, (original, restaurado)
    return f"12 archivos, restauración de prueba con {restaurado} filas"


def prueba_respaldo_fisico():
    """pg_basebackup genera un tar.gz con backup_label (lo que necesita PostgreSQL para arrancar)"""
    archivo = respaldos.respaldo_fisico("alajuela")
    with tarfile.open(archivo, "r:gz") as tar:
        nombres = tar.getnames()
    assert "backup_label" in nombres and "PG_VERSION" in nombres, nombres[:10]
    assert any(n.startswith("pg_wal/") for n in nombres), "no trae WAL"
    return f"{len(nombres)} archivos en el tar"


def prueba_wal_archivado():
    """El archivado de WAL funciona en los 6 nodos sin fallas"""
    for nodo in NODOS:
        nombre = respaldos.forzar_archivo_wal(nodo)
        fallidos = contar(nodo, "SELECT failed_count FROM pg_stat_archiver")
        assert fallidos == 0, f"{nodo}: {fallidos} fallas de archivado"
    return "6 nodos, 0 fallas"


def prueba_escenario_a_pitr():
    """Escenario A: borrado por error en San Carlos -> PITR al instante anterior"""
    resultado, diferentes, tiempos = escenarios.escenario_a()
    revisar(resultado, diferentes)
    return f"restaurar {tiempos['restaurar']:.0f} s + resincronizar {tiempos['resincronizar']:.0f} s"


def prueba_escenario_b_fisico():
    """Escenario B: se pierde Limón -> respaldo físico + WAL + reenganche"""
    resultado, diferentes, tiempos = escenarios.escenario_b("fisico")
    revisar(resultado, diferentes)
    return f"{tiempos['total']:.0f} s desde la falla"


def prueba_escenario_b_desde_central():
    """Escenario B: se pierde Limón -> nodo nuevo recuperado con replicación lógica desde el central"""
    resultado, diferentes, tiempos = escenarios.escenario_b("desde_central")
    revisar(resultado, diferentes)
    return f"{tiempos['total']:.0f} s desde la falla"


PRUEBAS = [
    prueba_respaldo_logico,
    prueba_respaldo_fisico,
    prueba_wal_archivado,
    prueba_escenario_a_pitr,
    prueba_escenario_b_fisico,
    prueba_escenario_b_desde_central,
]
