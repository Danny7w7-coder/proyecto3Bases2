# SIG-TEC

Sistema distribuido de información geográfica de los 5 campus del TEC.
6 nodos PostgreSQL + PostGIS en Docker: 1 central y 5 campus.

## Requisitos

- Docker Desktop (con el motor encendido)
- Python 3.10 o superior con `psycopg2` (`pip install psycopg2-binary`)

## Levantar todo

1. Abrir Docker Desktop.
2. Entrar a la carpeta `sig-tec/`.
3. Revisar `.env` (SRID, puertos y claves de prueba).
4. `python scripts/init_all.py --reset` (la primera vez descarga la imagen).
5. `python scripts/estado_nodos.py` debe terminar con `TODO OK`.

Para volver a aplicar los SQL sin borrar nada: `python scripts/init_all.py`.

## Comandos útiles

| Comando | Qué hace |
|---|---|
| `python scripts/correr_pruebas.py` | Todas las pruebas automáticas (OK / FALLO) |
| `python scripts/verificar_consistencia.py` | Compara las 40 capas en los 6 nodos y muestra el retraso de la replicación |
| `python scripts/replicacion.py estado` | Publicaciones y suscripciones de cada nodo |
| `python scripts/replicacion.py reactivar` | Relanza suscripciones que quedaron sin proceso (por ejemplo tras reiniciar nodos) |
| `python scripts/modo_sincrono.py demo` | Comparación asíncrono / síncrono (apaga y enciende el central) |
| `python scripts/demo_2pc.py` | Commit en dos fases entre el central y San Carlos |
| `python scripts/cargar_datos.py --forzar` | Recarga los datos de ejemplo |

## Nodos

| Nodo | Contenedor | Puerto |
|---|---|---|
| central | sigtec_central | 5440 |
| cartago | sigtec_cartago | 5441 |
| san_jose | sigtec_san_jose | 5442 |
| san_carlos | sigtec_san_carlos | 5443 |
| alajuela | sigtec_alajuela | 5444 |
| limon | sigtec_limon | 5445 |

Base: `sigtec`. Usuario: `postgres`. Clave: la de `.env` (solo para pruebas).

Cada campus tiene además el rol `sigtec_<campus>` (clave `EDITOR_PASSWORD` del `.env`).
Ese rol lee todo y solo edita a través de las vistas `sig.*`.
