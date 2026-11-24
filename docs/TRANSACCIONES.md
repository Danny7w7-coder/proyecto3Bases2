# Replicación y transacciones distribuidas

## 1. Replicación en dos niveles

```
              NIVEL 1 (campus -> central)                 NIVEL 2 (central -> campus)

  cartago    --pub_nivel1_cartago-->     +---------+   --pub_nivel2_cartago-->    cartago    (recibe sj, sc, al, li)
  san_jose   --pub_nivel1_san_jose-->    |         |   --pub_nivel2_san_jose-->   san_jose   (recibe ca, sc, al, li)
  san_carlos --pub_nivel1_san_carlos-->  | CENTRAL |   --pub_nivel2_san_carlos--> san_carlos (recibe ca, sj, al, li)
  alajuela   --pub_nivel1_alajuela-->    |         |   --pub_nivel2_alajuela-->   alajuela   (recibe ca, sj, sc, li)
  limon      --pub_nivel1_limon-->       +---------+   --pub_nivel2_limon-->      limon      (recibe ca, sj, sc, al)
```

- **Nivel 1:** cada campus publica su esquema (`FOR TABLES IN SCHEMA <campus>`). El central tiene 5 suscripciones y guarda cada campus en su propio esquema.
- **Nivel 2:** el central tiene una publicación por campus con los **otros 4** esquemas. Cada campus tiene una suscripción al central.
- Un campus nunca recibe su propio esquema. Así no hay bucles ni choques.
- Un cambio en San Carlos viaja así: San Carlos → central (nivel 1) → los otros 4 campus (nivel 2). El central lo reenvía porque las suscripciones usan `origin = any`, que es el valor por defecto.
- Si un nodo intentara escribir en una copia, el trigger `tg_solo_dueno` lo rechaza. Ese trigger no se dispara con los datos que llegan por replicación.
- Los scripts son `scripts/replicacion.py` (para crear, ver estado o quitar) y `scripts/verificar_consistencia.py`.

## 2. Atomicidad y orden

La replicación lógica envía una transacción **completa y solo después del COMMIT**. El suscriptor la aplica también como una sola transacción.

| Prueba (`tests/test_replicacion.py`) | Resultado |
|---|---|
| INSERT en San Carlos aparece en el central y en los otros 4 campus | OK, en menos de 1 s |
| UPDATE y DELETE se replican (`REPLICA IDENTITY` = clave primaria) | OK |
| Un edificio y 4 luminarias en un solo `BEGIN/COMMIT`: en el central nunca se ven a medias | OK |
| Un `ROLLBACK` no aparece en ningún nodo | OK |
| Una transacción `PREPARE TRANSACTION` no se replica hasta el `COMMIT PREPARED` | OK |

## 3. Modo asíncrono contra síncrono

Comando: `python scripts/modo_sincrono.py demo` (campus San Carlos).

| | Asíncrono (por defecto) | Síncrono |
|---|---|---|
| COMMIT promedio con el central arriba | ~4 a 10 ms | ~8 ms |
| Síncrono con la suscripción por defecto | | ~220 ms |
| COMMIT con el central caído | 0.01 s (sigue trabajando) | **se queda esperando** (`wait_event = SyncRep`) hasta que vuelve el central |
| Si se pierde el campus justo después del COMMIT | el último cambio puede no haber llegado al central | el cambio ya está en el central |

**Cómo se activa:**
- En el campus: `synchronous_standby_names = 'sub_nivel1_<campus>'` y `synchronous_commit = on`. Se usa `ALTER SYSTEM` + `pg_reload_conf()`, sin reiniciar.
- En el central: `ALTER SUBSCRIPTION sub_nivel1_<campus> SET (synchronous_commit = on)`.

**Lo que encontramos:** al principio el modo síncrono tardaba ~220 ms por COMMIT. Una suscripción usa `synchronous_commit = off` por defecto. Por eso el central confirma solo cuando el *WAL writer* escribe a disco, y eso pasa cada `wal_writer_delay` (200 ms). Al poner la suscripción en `on`, el central confirma apenas guarda y el COMMIT bajó a ~8 ms. La demo muestra las dos mediciones.

**Conclusión:** el modo asíncrono da **autonomía**, porque el campus funciona aunque el central se caiga. El síncrono da **más seguridad** pero ata la disponibilidad del campus a la del central. Por eso el sistema usa asíncrono por defecto.

## 4. Commit en dos fases (2PC)

Comando: `python scripts/demo_2pc.py`. Caso: registrar un usuario en el **central** y crear su punto de interés "Oficina de …" en el nodo de **San Carlos**, los dos juntos o ninguno.

| Escenario | Qué pasa | Resultado (central, campus) |
|---|---|---|
| a) Éxito | Los dos nodos hacen `PREPARE TRANSACTION`, luego `COMMIT PREPARED` en ambos | (1, 1) |
| b) Falla en el campus | El INSERT del campus viola un CHECK, luego `ROLLBACK` en ambos | (0, 0) |
| c) Cae el coordinador después de preparar | Quedan pendientes en `pg_prepared_xacts` de los dos nodos y los datos no se ven. Un coordinador nuevo usa `tpc_recover()` y como ambos estaban preparados hace `COMMIT PREPARED` | (0, 0) y después (1, 1) |

Se usa la API de psycopg2: `tpc_begin`, `tpc_prepare`, `tpc_commit`, `tpc_rollback` y `tpc_recover`. Requiere `max_prepared_transactions > 0`, que vale 20 en el `docker-compose.yml`.

**Relación con la replicación:** la fila preparada en San Carlos se replica al central y a los otros campus **solo después** del `COMMIT PREPARED`. Si se hace `ROLLBACK PREPARED`, nunca sale del nodo.

## 5. Verificación de consistencia

`python scripts/verificar_consistencia.py` compara las 40 capas (5 esquemas × 8 capas) en los 6 nodos. Para cada capa usa el conteo de filas y un md5 de todas las filas ordenadas por id. Muestra OK o DIFERENTE por capa, y el retraso de cada publicador y suscriptor.

Nota: `apply_error_count` de `pg_stat_subscription_stats` también cuenta las veces que el publicador estuvo caído, y nunca vuelve a cero. Por eso la prueba de salud revisa que el proceso de cada suscripción esté corriendo (`pg_stat_subscription.pid`).
