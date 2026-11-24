# Instalar y probar el plugin SIG-TEC en QGIS

Probado con QGIS 3.44.15 LTR en Windows. Funciona desde QGIS 3.22 y está preparado para QGIS 4 (Qt6).

## 1. Antes de empezar

1. Docker Desktop abierto y los nodos arriba: `python scripts/init_all.py`
2. `python scripts/estado_nodos.py` termina con `TODO OK`
3. Generar el paquete: `python scripts/empaquetar_plugin.py` → crea `dist/sigtec.zip`

No hace falta instalar nada en QGIS. El plugin usa `psycopg2`, que ya viene con QGIS para Windows. Si no estuviera, usa la conexión propia de QGIS de forma automática.

## 2. Instalar

1. Abrir **QGIS Desktop**.
2. Menú **Complementos → Administrar e instalar complementos…**
3. A la izquierda, **Instalar a partir de ZIP**.
4. Elegir `dist/sigtec.zip` → **Instalar complemento**.
5. Si pregunta por complementos no confiables, aceptar. Es nuestro.
6. Aparece un botón azul con un marcador y la palabra **TEC** en la barra de herramientas, y el menú **Complementos → SIG-TEC**.

**Para actualizar** después de cambiar el código: volver a empaquetar e instalar el zip otra vez. Si QGIS no toma el cambio, cerrar y abrir QGIS.

**Configuración:** `config.ini` (dentro del plugin) tiene la dirección del central (`localhost:5440`). Si el central está en otra máquina, cambiarla ahí.

## 3. Prueba manual (≈ 5 minutos)

Usuarios de ejemplo (clave `tec2026`): `cartago1`, `sanjose1`, `sancarlos1`, `alajuela1`, `limon1`.

| # | Qué hacer | Qué debe pasar |
|---|---|---|
| 1 | Clic en el botón **TEC** | Se abre la ventana "SIG-TEC - Ingreso" con usuario, contraseña e Ingresar |
| 2 | Usuario `sancarlos1`, clave `mala`, **Ingresar** | Mensaje en rojo: *Usuario o contraseña incorrectos.* La ventana sigue abierta |
| 3 | Usuario `inactivo1`, clave `tec2026` | Mensaje: *El usuario inactivo1 está inactivo.* |
| 4 | Usuario `sancarlos1`, clave `tec2026` | La ventana se cierra. Aparece el grupo **SIG-TEC - Campus Tecnológico Local San Carlos** con 8 capas. El mapa se acerca al campus. Mensaje verde de bienvenida |
| 5 | Mirar el mapa | Edificios café con su nombre, zonas verdes, parqueos grises, calles, aceras, accesibilidad azul punteada, puntos de interés y luminarias con colores por tipo/estado |
| 6 | Alejar el mapa (rueda del mouse) hasta ver todo Costa Rica | Se ven los datos de los 5 campus (Cartago, San José, San Carlos, Alajuela, Limón) |
| 7 | Clic derecho en **Edificios** → **Conmutar edición**. Herramienta **Identificar**, clic en un edificio de San Carlos y cambiar `pisos`. **Guardar ediciones** | Se guarda sin error |
| 8 | Ir a Cartago, editar un edificio de Cartago (por ejemplo la Biblioteca) y **Guardar** | QGIS no guarda. Mensaje rojo del plugin: *No puede modificar el objeto … porque pertenece al Campus Tecnológico Central Cartago…*. Usar **Descartar ediciones** |
| 9 | En **Puntos de interés**, con edición activa, **Añadir entidad de punto** en San Carlos. Llenar nombre y tipo (`soda`) y guardar | Se guarda con `campus_id` 3 y un id 3 000 xxx |
| 10 | Salir con `sancarlos1`, entrar con `cartago1` | El grupo cambia a Cartago (no se duplican las capas). El punto del paso 9 se ve también desde Cartago |
| 11 | Abrir la **tabla de atributos** de cualquier capa | Están las filas de los 5 campus. La columna `campus_id` indica el dueño |

**Si algo falla en la prueba manual**, revisar **Ver → Paneles → Registro de mensajes**, pestañas *SIG-TEC*, *PostGIS* y *Python warning*.

## 4. Lo que ya está probado automáticamente

`python scripts/correr_pruebas.py plugin` corre:

- `test_plugin_logica.py`: la lógica sin QGIS. Configuración, login bueno o malo, servidor caído, estilos, mensajes de error e inyección SQL.
- `test_plugin_qgis.py`: el plugin **dentro de QGIS** (con el Python de QGIS, sin abrir la ventana principal). Son 12 pruebas: carga del plugin, ventana de login con clave buena o mala, 8 capas con SRID 5367 y clave `id`, estilos aplicados, mapa centrado, edición propia guardada, edición o borrado ajeno rechazado con mensaje, alta y baja de un punto, conexión de respaldo sin psycopg2, cambio de usuario sin duplicar capas y `unload()`.

Y en la **ventana real de QGIS** (con interfaz, no sin pantalla):

```powershell
$env:SIGTEC_CAPTURAS = "C:\ruta\para\capturas"
& "C:\Program Files\QGIS 3.44.15\bin\qgis-ltr.bat" --nologo --code "$PWD\tests\qgis\prueba_ventana_qgis.py"
```

Antes hay que instalar el plugin en el perfil, con "Instalar a partir de ZIP" o descomprimiendo `dist/sigtec.zip` en `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins`. El script abre QGIS y hace los pasos 1 a 10 de la tabla de arriba con la ventana, la barra de mensajes y el mapa reales. Guarda una captura en cada paso y el resultado en `resultado.txt`, y al final cierra QGIS. Después hay que borrar el punto "Soda de prueba QGIS" y devolver Laboratorios a 1 piso, o correr `python scripts/cargar_datos.py --forzar`.

Lo único que no se prueba automáticamente es mover el mouse. Eso es la prueba manual de arriba.
