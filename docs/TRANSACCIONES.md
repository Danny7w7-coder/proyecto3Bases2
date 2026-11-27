# Replicación y transacciones distribuidas

Cómo viajan los datos entre los seis servidores de SIG-TEC y cómo se garantiza que lleguen completos y en orden.

[← Volver al README](../README.md)

---

## Tabla de contenidos

1. [Antes de empezar](#1-antes-de-empezar)
2. [Replicación en dos niveles](#2-replicación-en-dos-niveles)
3. [Comprobar que las copias son iguales](#3-comprobar-que-las-copias-son-iguales)
4. [Atomicidad: todo o nada](#4-atomicidad-todo-o-nada)
5. [Modo asíncrono y modo síncrono](#5-modo-asíncrono-y-modo-síncrono)
6. [Commit en dos fases (2PC)](#6-commit-en-dos-fases-2pc)
7. [Resumen de comandos](#7-resumen-de-comandos)

---

## 1. Antes de empezar

Todos los comandos de esta guía se ejecutan en la terminal, dentro de la carpeta del proyecto, con el sistema levantado. Para comprobarlo:

```powershell
python scripts/estado_nodos.py
```

Debe terminar con `TODO OK`. Si no, siga el [README, sección 3](../README.md#3-instalación-paso-a-paso).

---

## 2. Replicación en dos niveles

### 2.1 Por qué dos niveles

PostgreSQL **no permite** que varios servidores escriban sobre la misma tabla replicada (replicación *multimaestro*). Por eso SIG-TEC sigue una regla simple: **cada dato tiene un solo dueño**. Los datos de San Carlos solo se crean, modifican y borran en el servidor de San Carlos. Los demás servidores reciben una **copia de solo consulta**.

### 2.2 Cómo viajan los datos

```
              NIVEL 1 (campus → central)                   NIVEL 2 (central → campus)

  Cartago    ── envía su esquema ──►   ┌─────────┐   ── los otros 4 ──►   Cartago
  San José   ── envía su esquema ──►   │         │   ── los otros 4 ──►   San José
  San Carlos ── envía su esquema ──►   │ CENTRAL │   ── los otros 4 ──►   San Carlos
  Alajuela   ── envía su esquema ──►   │         │   ── los otros 4 ──►   Alajuela
  Limón      ── envía su esquema ──►   └─────────┘   ── los otros 4 ──►   Limón
```

| Nivel | Quién publica | Qué publica | Quién se suscribe |
|---|---|---|---|
| **1** | Cada campus (`pub_nivel1_<campus>`) | Las 8 capas de su propio esquema | El nodo central (5 suscripciones) |
| **2** | El nodo central (`pub_nivel2_<campus>`) | Los esquemas de los **otros 4** campus y los estilos de QGIS | Cada campus (1 suscripción) |

**Ejemplo:** un edificio nuevo en San Carlos viaja de San Carlos al central (nivel 1). Luego va del central a Cartago, San José, Alajuela y Limón (nivel 2). Tarda menos de un segundo.

### 2.3 Reglas que evitan conflictos

- **Un campus nunca recibe su propio esquema.** Así un dato no puede "dar la vuelta" y volver a su origen.
- **Las copias son de solo lectura.** Un disparador (`tg_solo_dueno`) rechaza cualquier escritura en un esquema que no es del servidor. Ese disparador no afecta a los datos que llegan por replicación.
- Cada fila se identifica por su clave primaria `id`, así que las modificaciones y los borrados también se replican.

### 2.4 Cómo verlo

```powershell
python scripts/replicacion.py estado
```

Muestra en cada servidor sus publicaciones (qué envía) y sus suscripciones (qué recibe). Todas deben decir **(activa)**.

---

## 3. Comprobar que las copias son iguales

```powershell
python scripts/verificar_consistencia.py
```

**Qué hace:** compara las **40 capas** (5 campus × 8 capas) en los **6 servidores**. Para cada capa cuenta las filas y calcula un resumen (hash md5) de todo su contenido.

**Qué debe mostrar:**

- Una tabla con una fila por capa, la cantidad de objetos en cada servidor y la palabra **OK**.
- El retraso de cada publicación y suscripción. Normalmente es 0.
- Al final: `40 capas OK, 0 DIFERENTES`.

Para ver solo el resultado final: `python scripts/verificar_consistencia.py --resumen`

---

## 4. Atomicidad: todo o nada

La replicación envía cada transacción **completa** y **solo después de confirmarla** (`COMMIT`). El servidor que la recibe también la aplica completa. Esto se comprobó con pruebas automáticas (`python scripts/correr_pruebas.py replicacion`):

| Prueba | Resultado |
|---|---|
| Un objeto nuevo en San Carlos aparece en el central y en los otros 4 campus | Correcto, en menos de 1 segundo |
| Las modificaciones y los borrados también se replican | Correcto |
| Un edificio y 4 luminarias guardados en una sola transacción: en el central nunca se ven a medias | Correcto |
| Una transacción cancelada (`ROLLBACK`) no aparece en ningún servidor | Correcto |
| Una transacción preparada (`PREPARE TRANSACTION`) no se replica hasta que se confirma | Correcto |

---

## 5. Modo asíncrono y modo síncrono

### 5.1 Qué significa cada uno

| | **Asíncrono** (el que usa el sistema) | **Síncrono** |
|---|---|---|
| Cuándo termina el `COMMIT` del campus | Apenas el dato queda guardado en el campus | Cuando además el central confirma que lo recibió |
| Si el central se cae | El campus **sigue trabajando** | El `COMMIT` del campus **se queda esperando** |
| Si el campus se pierde justo después de guardar | El último cambio podría no haber llegado al central | El cambio ya está en el central |

### 5.2 Demostración

```powershell
python scripts/modo_sincrono.py demo
```

**Duración:** entre 40 y 60 segundos. **Atención:** apaga y enciende el nodo central durante la prueba.

**Resultados medidos** (San Carlos, 100 confirmaciones):

| Medición | Asíncrono | Síncrono |
|---|---|---|
| Tiempo promedio de un `COMMIT` con el central encendido | 3.97 ms | 7.03 ms |
| Lo mismo, con la configuración por defecto de PostgreSQL | | 230.75 ms |
| `COMMIT` con el central apagado | 0.02 s (sigue trabajando) | Espera hasta que el central vuelve (6.69 s en la prueba) |

**Hallazgo.** Con la configuración por defecto, el modo síncrono tardaba unos 230 ms por confirmación. El central solo confirmaba cada 200 ms, porque su suscripción tiene `synchronous_commit = off`. Al activarlo, bajó a unos 7 ms.

**Conclusión.** El modo asíncrono da **autonomía** a cada campus, porque sigue funcionando aunque el central falle. El síncrono da **más seguridad**, pero hace que cada campus dependa del central. Por eso el sistema usa el modo asíncrono.

### 5.3 Activarlo o desactivarlo a mano

```powershell
python scripts/modo_sincrono.py activar san_carlos      # un campus (o "todos")
python scripts/modo_sincrono.py estado                  # ver cómo está cada campus
python scripts/modo_sincrono.py desactivar todos        # volver al modo asíncrono
```

---

## 6. Commit en dos fases (2PC)

### 6.1 Qué resuelve

Algunas operaciones deben quedar hechas en **dos servidores a la vez**, o en ninguno. El caso del proyecto es **registrar un usuario nuevo en el nodo central** y, al mismo tiempo, **crear su punto de interés "Oficina de…" en el servidor de su campus**.

El commit en dos fases funciona así:

1. **Fase 1, preparar.** Cada servidor hace su parte y responde "estoy listo" (`PREPARE TRANSACTION`). Un servidor preparado garantiza que podrá confirmar, incluso si se reinicia.
2. **Fase 2, decidir.** Si **todos** respondieron que sí, se confirma en todos (`COMMIT PREPARED`). Si **alguno** falló, se cancela en todos (`ROLLBACK PREPARED`).

### 6.2 Demostración

```powershell
python scripts/demo_2pc.py
```

**Duración:** unos 5 segundos. Muestra tres casos:

| Caso | Qué pasa | Resultado (central, campus) |
|---|---|---|
| **a) Éxito** | Los dos servidores preparan y se confirma en ambos | (1, 1): el dato está en los dos |
| **b) Falla en el campus** | El dato del campus no es válido. Se cancela en ambos | (0, 0): no queda nada en ninguno |
| **c) Se cae el coordinador** | Los dos preparan y el coordinador se cae antes de decidir. Las transacciones quedan pendientes en ambos servidores. Un coordinador nuevo las encuentra y las confirma | (0, 0) y después (1, 1) |

Al final, el script borra los datos de la demostración.

**Relación con la replicación:** el punto de interés preparado en San Carlos se replica a los demás servidores **solo después** de confirmarse. Si se cancela, nunca sale de San Carlos.

---

## 7. Resumen de comandos

| Comando | Qué hace |
|---|---|
| `python scripts/replicacion.py estado` | Muestra las publicaciones y suscripciones |
| `python scripts/verificar_consistencia.py` | Compara las 40 capas en los 6 servidores |
| `python scripts/modo_sincrono.py demo` | Compara el modo asíncrono con el síncrono |
| `python scripts/demo_2pc.py` | Muestra el commit en dos fases |
| `python scripts/replicacion.py reactivar` | Relanza la replicación si quedó detenida, por ejemplo después de reiniciar servidores |
| `python scripts/correr_pruebas.py replicacion` | Pruebas automáticas de replicación |
| `python scripts/correr_pruebas.py transacciones` | Pruebas automáticas de transacciones |
