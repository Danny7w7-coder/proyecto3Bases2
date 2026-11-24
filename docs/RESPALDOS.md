# Respaldo y recuperación

Cada nodo tiene su propia estrategia. Todo se maneja con scripts de Python en `scripts/`.

## 1. Mecanismos

| Mecanismo | Cómo | Comando | Dónde queda |
|---|---|---|---|
| Respaldo lógico | `pg_dump -Fc` de la base completa y del esquema propio del nodo (`public` en el central) | `python scripts/respaldos.py logico [nodo\|todos]` | `backups/<nodo>/logico/<nodo>_completo_<fecha>.dump` y `<nodo>_esquema_<esquema>_<fecha>.dump` |
| Verificación del lógico | Se restaura el último `.dump` completo en una base nueva (`verificacion_respaldo`) y se comparan las filas tabla por tabla | `python scripts/respaldos.py verificar <nodo>` | La base de prueba se borra al terminar |
| Respaldo físico | `pg_basebackup -D - -Ft -z -X fetch -c fast`: un `.tar.gz` con todo el cluster y el WAL necesario | `python scripts/respaldos.py fisico [nodo\|todos]` | `backups/<nodo>/fisico/<nodo>_base_<fecha>.tar.gz` |
| WAL | `archive_mode = on` y `archive_command = 'test ! -f /wal_archive/%f && cp %p /wal_archive/%f'`. Con `archive_timeout = 60` se archiva al menos un segmento por minuto | Automático. Estado en `python scripts/respaldos.py listar` | Volumen `<nodo>_wal`, aparte del volumen de datos |
| PITR | Respaldo físico + WAL hasta `recovery_target_time` | `python scripts/restaurar.py pitr <campus> "<hora UTC>"` | |
| Recuperación con replicación lógica | Nodo nuevo y vacío. Su esquema se rescata de la copia del central (publicación y suscripción temporales) | `python scripts/restaurar.py desde_central <campus>` | |
| Prueba de recuperación | Falla simulada: se borran el contenedor y el volumen de datos | `python scripts/simular_falla.py <campus>` | |

Los respaldos se guardan en el anfitrión porque el comando corre dentro del contenedor (`docker exec`) y su salida se escribe directo en el archivo. No hace falta montar carpetas de Windows.

## 2. Restauración física paso a paso (`scripts/restaurar.py`)

1. Si el nodo está vivo, `pg_switch_wal()` y esperar a que ese WAL quede archivado.
2. `docker compose stop <nodo>`
3. Un contenedor auxiliar vacía el volumen de datos y descomprime el respaldo. El `.tar.gz` le llega por la entrada estándar.
4. Se crea `recovery.signal` y se agrega a `postgresql.auto.conf`:
   ```
   restore_command = 'cp /wal_archive/%f %p'
   recovery_target_time = '2026-11-24 20:00:11+00'   # solo en PITR
   recovery_target_action = 'promote'
   ```
5. `docker compose start <nodo>`. PostgreSQL aplica el WAL. En PITR se detiene justo antes de la primera transacción posterior a la hora indicada. Después se promueve a un **timeline** nuevo.
6. `ALTER SYSTEM RESET` de esos tres parámetros.

## 3. Reenganche de la replicación (`replicacion.py resincronizar <campus>`)

Restaurar un nodo **rompe su replicación lógica**:
- `pg_basebackup` **no copia los slots de replicación**, así que el central ya no puede leer del nodo restaurado.
- El nodo restaurado puede estar **"más atrás"** que lo que ya tiene el central. Por ejemplo, en PITR el central ya recibió el borrado erróneo.

La regla es que **el nodo restaurado manda sobre su esquema** y **el central manda sobre los demás**:

1. Se sueltan las suscripciones viejas del campus (`DISABLE` + `slot_name = NONE` + `DROP`) y los slots huérfanos.
2. En el central se vacía la copia de ese campus. El `TRUNCATE` viaja a los otros 4 campus por el nivel 2.
3. En el campus se vacían las copias de los otros 4 y los estilos.
4. Se crean otra vez las suscripciones con `copy_data = true`, primero el nivel 1 y luego el nivel 2.

`TRUNCATE` se hace con `session_replication_role = replica`, para que los triggers de protección no lo bloqueen. Es lo mismo que hace la replicación al aplicar datos.

## 4. Escenarios demostrables

`python scripts/escenarios.py a`, `python scripts/escenarios.py b fisico` y `python scripts/escenarios.py b desde_central`. Los tres también corren en `tests/test_respaldos.py`.

### Escenario A: se borran datos por error en San Carlos → PITR

| Paso | Qué pasa |
|---|---|
| 1 | Respaldo físico de San Carlos |
| 2 | Se crea un edificio **después** del respaldo |
| 3 | Se anota la hora T (`SELECT now()`) |
| 4 | **Error:** `DELETE` de todos los puntos de interés y luminarias. **El borrado se replica** al central y a Cartago en menos de 1 s. La replicación no protege contra errores humanos |
| 5 | PITR hasta T. El log dice: *recovery stopping before commit of transaction …*, es decir, se detuvo justo antes del DELETE |
| 6 | Resincronización. Los datos vuelven también al central y a los otros campus |
| Resultado | 7 puntos y 8 luminarias de vuelta. **El edificio del paso 2 sigue** (lo recuperó el WAL). 40 capas OK |
| Tiempos | Restaurar + WAL: ~6 s. Resincronizar: ~4 a 7 s |

Lo que se hizo en San Carlos entre T y el PITR se pierde. Eso es lo que significa volver a un instante.

### Escenario B: se pierde el nodo de Limón completo

| Paso | Qué pasa |
|---|---|
| 1 | (modo `fisico`) Respaldo físico de Limón |
| 2 | Se crea un punto de interés nuevo. Llega al central y se archiva su WAL |
| 3 | **Falla:** `docker compose rm -s -f limon` + `docker volume rm sig-tec_limon_data` |
| 4a | **Modo `fisico`:** último respaldo + todo el WAL archivado + resincronización |
| 4b | **Modo `desde_central`:** contenedor nuevo, `initdb`, los SQL del proyecto, rescate del esquema `limon` desde el central, `setval` de la secuencia y resincronización |
| Resultado | El punto del paso 2 está, la vista muestra los 5 campus, una edición nueva llega a Cartago y las 40 capas están OK |
| Tiempos | `fisico`: ~9 a 13 s desde la falla. `desde_central`: ~13 a 26 s |

**Comparación de los dos modos:**

| | Físico + WAL | Desde el central |
|---|---|---|
| Depende de | Respaldos propios del nodo (independiente del central) | Que el central esté vivo y al día |
| Puede perder | Lo que no alcanzó a archivarse (hasta 60 s con `archive_timeout = 60`) | Nada que ya haya llegado al central |
| Recupera | Todo el cluster: roles, configuración, historial | Solo los datos. La estructura se rehace con los SQL del proyecto |
| Detalle | Abre un timeline nuevo | El WAL viejo del nodo se aparta a `/wal_archive/anterior_<fecha>/`, porque el nodo nuevo reinicia la numeración |

## 5. Notas

- En el proyecto el volumen del WAL está en la misma máquina. En producción estaría en **otro disco u otro servidor**, porque si se pierde junto con los datos no hay PITR posible.
- Después de un PITR conviene sacar un respaldo físico nuevo, porque el nodo está en otro timeline.
- `backups/` está en `.gitignore`: los respaldos no van al repositorio ni al zip de entrega.
