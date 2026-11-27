# Respaldo y recuperación

Cómo se respaldan los seis servidores de SIG-TEC y cómo se recupera un servidor ante un error o una falla.

[← Volver al README](../README.md)

---

## Tabla de contenidos

1. [Antes de empezar](#1-antes-de-empezar)
2. [Mecanismos de respaldo](#2-mecanismos-de-respaldo)
3. [Hacer respaldos](#3-hacer-respaldos)
4. [Escenario A: borrado por error y recuperación a un instante (PITR)](#4-escenario-a-borrado-por-error-y-recuperación-a-un-instante-pitr)
5. [Escenario B: pérdida completa de un servidor](#5-escenario-b-pérdida-completa-de-un-servidor)
6. [Recuperar a mano, paso a paso](#6-recuperar-a-mano-paso-a-paso)
7. [Cómo funciona por dentro](#7-cómo-funciona-por-dentro)
8. [Resumen de comandos](#8-resumen-de-comandos)

---

## 1. Antes de empezar

- Todos los comandos se ejecutan en la terminal, dentro de la carpeta del proyecto, con el sistema levantado (`python scripts/estado_nodos.py` debe terminar con `TODO OK`).
- **Atención:** los escenarios de esta guía **apagan, borran y restauran servidores de verdad**. Es seguro hacerlo, porque todo vuelve a quedar bien. Aun así, no los ejecute mientras otra persona usa el sistema.
- Los respaldos se guardan en la carpeta `backups/` del proyecto. Esa carpeta no se sube al repositorio.

---

## 2. Mecanismos de respaldo

Cada servidor tiene su propia estrategia de respaldo:

| Mecanismo | Qué es | Para qué sirve |
|---|---|---|
| **Respaldo lógico** (`pg_dump`) | Una copia de la base completa y otra del esquema propio del servidor | Restaurar tablas o datos puntuales. Se puede abrir en otro servidor |
| **Respaldo físico** (`pg_basebackup`) | Una copia exacta de todos los archivos del servidor, comprimida | Reconstruir un servidor completo |
| **WAL archivado** | El registro de **cada cambio** que se hace en la base. Se copia continuamente a un espacio aparte, al menos una vez por minuto | Junto con el respaldo físico, permite volver a **cualquier instante** (PITR) |
| **Replicación lógica** | Las copias que el central tiene de cada campus | Recuperar un campus desde el central sin usar respaldos |

---

## 3. Hacer respaldos

| Comando | Qué hace | Resultado esperado |
|---|---|---|
| `python scripts/respaldos.py logico todos` | Respaldo lógico de los 6 servidores | Dos archivos `.dump` por servidor en `backups/<nodo>/logico/` |
| `python scripts/respaldos.py verificar cartago` | Restaura el último respaldo lógico de Cartago en una base de prueba y compara las filas | `... restaurado en 'verificacion_respaldo': N filas (original N) -> OK` |
| `python scripts/respaldos.py fisico todos` | Respaldo físico de los 6 servidores | Un archivo `.tar.gz` por servidor en `backups/<nodo>/fisico/` (unos 7.5 MB, 2 segundos cada uno) |
| `python scripts/respaldos.py listar` | Lista los respaldos y el estado del WAL archivado | Los archivos guardados y, por servidor, cuántos WAL se archivaron y cuántos fallaron (debe ser 0) |

En lugar de `todos` se puede indicar un solo servidor: `central`, `cartago`, `san_jose`, `san_carlos`, `alajuela` o `limon`.

---

## 4. Escenario A: borrado por error y recuperación a un instante (PITR)

**Situación:** alguien borra por error todos los puntos de interés y las luminarias de San Carlos. Como la replicación copia todo, **el error también llega al central y a los demás campus en menos de un segundo**. La replicación no protege contra errores humanos. Para eso está la recuperación a un instante (PITR).

**Comando:**

```powershell
python scripts/escenarios.py a
```

**Duración:** entre 20 y 50 segundos. El script muestra cada paso:

| Paso | Qué ocurre |
|---|---|
| A.1 | Se hace un respaldo físico de San Carlos |
| A.2 | Se crea un edificio nuevo **después** del respaldo y se anota la hora exacta |
| A.3 | **El error:** se borran los puntos de interés y las luminarias. El borrado aparece también en el central y en Cartago |
| A.4 | Se restaura San Carlos con el respaldo físico y se aplica el WAL **hasta un segundo antes del borrado**. El registro de PostgreSQL dice *"recovery stopping before commit of transaction…"*, es decir, se detuvo justo antes del error. Después se vuelve a enganchar la replicación |
| A.5 | Comprobación |

**Resultado esperado (A.5):**

```
  puntos               7 (esperado 7) OK
  luminarias           8 (esperado 8) OK
  puntos_en_cartago    7 (esperado 7) OK
  edificio_posterior   1 (esperado 1) OK
  consistencia: 40 capas OK
```

- Los datos borrados volvieron **en los seis servidores**.
- El edificio creado **después** del respaldo también está. Lo recuperó el WAL.
- Lo que se hubiera hecho en San Carlos entre el error y la recuperación se pierde. Eso es lo que significa volver a un instante.

---

## 5. Escenario B: pérdida completa de un servidor

**Situación:** se pierde por completo el servidor de Limón. Se borran su contenedor y su disco de datos.

Hay **dos formas** de recuperarlo:

### 5.1 Con el respaldo físico

```powershell
python scripts/escenarios.py b fisico
```

**Duración:** entre 20 y 45 segundos. Se hace un respaldo, se crea un punto de interés nuevo, se borra el servidor y se restaura con el **último respaldo físico más todo el WAL archivado**.

### 5.2 Desde el nodo central (replicación lógica)

```powershell
python scripts/escenarios.py b desde_central
```

**Duración:** entre 30 y 60 segundos. Se crea un servidor de Limón **nuevo y vacío**. Se le crean las tablas y sus datos se **rescatan de la copia que tiene el central**.

### 5.3 Resultado esperado (en los dos casos)

```
  punto_reciente       1 (esperado 1) OK
  puntos_limon         8 (esperado 8) OK
  vista_con_5_campus   5 (esperado 5) OK
  edicion_despues      1 (esperado 1) OK
  consistencia: 40 capas OK
```

Limón vuelve con todos sus datos, ve los cinco campus y se puede editar otra vez.

### 5.4 Comparación

| | Con respaldo físico | Desde el central |
|---|---|---|
| Depende de | Los respaldos del propio servidor | Que el central esté funcionando |
| Puede perder | Los cambios que no alcanzaron a archivarse (hasta 1 minuto) | Nada que ya haya llegado al central |
| Recupera | Todo el servidor: datos, usuarios y configuración | Los datos. La estructura se vuelve a crear con los scripts del proyecto |
| Tiempo medido (desde la falla) | 10 a 31 segundos | 21 a 43 segundos |

---

## 6. Recuperar a mano, paso a paso

Los escenarios anteriores hacen todo solos. Para hacer una recuperación manualmente:

### 6.1 Recuperación a un instante (PITR)

1. Antes de tener un problema, haga un respaldo físico:
   ```powershell
   python scripts/respaldos.py fisico san_carlos
   ```
2. Anote la hora del servidor. Está en hora UTC, seis horas más que la hora de Costa Rica:
   ```powershell
   docker exec sigtec_san_carlos psql -U postgres -d sigtec -tAc "SELECT now()::timestamptz(0)"
   ```
3. *(Ocurre el error.)*
4. Recupere el servidor hasta la hora anotada:
   ```powershell
   python scripts/restaurar.py pitr san_carlos "2026-11-24 20:11:23+00"
   ```

### 6.2 Servidor perdido

```powershell
python scripts/simular_falla.py limon          # simula la pérdida: borra el contenedor y sus datos
python scripts/restaurar.py fisico limon       # opción 1: con el último respaldo físico + WAL
python scripts/restaurar.py desde_central limon  # opción 2: desde la copia del central
```

Al final de cualquier recuperación, compruebe con:

```powershell
python scripts/verificar_consistencia.py --resumen
```

Debe decir `40 capas OK, 0 DIFERENTES`.

---

## 7. Cómo funciona por dentro

### 7.1 Restaurar un respaldo físico

1. Se detiene el servidor.
2. Se borran sus datos y se descomprime el respaldo en su lugar.
3. Se le indica a PostgreSQL **de dónde leer el WAL** y, en el caso de PITR, **hasta qué hora aplicarlo**:
   ```
   restore_command        = 'cp /wal_archive/%f %p'
   recovery_target_time   = '2026-11-24 20:11:23+00'
   recovery_target_action = 'promote'
   ```
4. Se enciende el servidor. PostgreSQL aplica los cambios del WAL hasta la hora indicada y queda listo para trabajar.

### 7.2 Volver a enganchar la replicación

Restaurar un servidor **rompe su replicación**, por dos razones:

- El respaldo físico **no incluye** los puntos de conexión de la replicación (*slots*).
- El servidor restaurado puede tener datos **más viejos** que los que ya recibió el central.

Por eso toda recuperación termina con una **resincronización**, que sigue una regla simple: **el servidor restaurado manda sobre sus propios datos, y el central manda sobre los de los demás.**

1. Se quitan las suscripciones viejas de ese campus.
2. El central vacía su copia de ese campus y la vuelve a copiar desde el servidor restaurado. Los otros campus reciben el cambio por el nivel 2.
3. El servidor restaurado vacía sus copias de los otros campus y las vuelve a copiar desde el central.

Se puede ejecutar sola: `python scripts/replicacion.py resincronizar limon`

### 7.3 Notas

- En este proyecto el WAL archivado está en la misma computadora, en un espacio aparte del de los datos. En una instalación real debería estar **en otro disco o en otro servidor**.
- Después de una recuperación a un instante, conviene hacer un respaldo físico nuevo.

---

## 8. Resumen de comandos

| Comando | Qué hace |
|---|---|
| `python scripts/respaldos.py logico todos` | Respaldo lógico de todos los servidores |
| `python scripts/respaldos.py fisico todos` | Respaldo físico de todos los servidores |
| `python scripts/respaldos.py verificar <nodo>` | Comprueba que el respaldo lógico se puede restaurar |
| `python scripts/respaldos.py listar` | Lista los respaldos y el estado del WAL |
| `python scripts/escenarios.py a` | Escenario A: borrado por error y PITR |
| `python scripts/escenarios.py b fisico` | Escenario B: servidor perdido, recuperado con respaldo físico |
| `python scripts/escenarios.py b desde_central` | Escenario B: servidor perdido, recuperado desde el central |
| `python scripts/restaurar.py pitr <campus> "<hora UTC>"` | Recupera un campus hasta una hora exacta |
| `python scripts/restaurar.py fisico <campus>` | Recupera un campus con su último respaldo físico |
| `python scripts/restaurar.py desde_central <campus>` | Recupera un campus desde la copia del central |
| `python scripts/simular_falla.py <campus>` | Simula la pérdida completa de un campus |
| `python scripts/replicacion.py resincronizar <campus>` | Vuelve a enganchar la replicación de un campus |
| `python scripts/correr_pruebas.py respaldos` | Pruebas automáticas de respaldo y recuperación |
