"""
Prueba del plugin en la VENTANA REAL de QGIS (con interfaz gráfica, no sin pantalla).

Se ejecuta al abrir QGIS:
    set SIGTEC_CAPTURAS=C:\\ruta\\para\\capturas
    qgis-ltr.bat --nologo --code tests/qgis/prueba_ventana_qgis.py

Hace los pasos de docs/INSTALAR_PLUGIN.md con el iface real de QGIS:
activa el plugin, usa la ventana de ingreso (clave mala, usuario inactivo, clave buena),
revisa capas, estilos y mapa, edita un objeto propio, intenta editar uno de Cartago,
crea un punto y entra con otro usuario. Guarda una captura de la ventana en cada paso
y el resultado en resultado.txt. Al final cierra QGIS.
"""
import os
import traceback

from qgis.core import QgsFeature, QgsFeatureRequest, QgsGeometry, QgsProject, QgsSettings
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.utils import iface, loadPlugin, plugins, startPlugin, updateAvailablePlugins

SALIDA = os.environ.get("SIGTEC_CAPTURAS", os.path.expanduser("~"))
os.makedirs(SALIDA, exist_ok=True)
registro = open(os.path.join(SALIDA, "resultado.txt"), "w", encoding="utf-8")
resultados = []


def escribir(texto):
    """Escribe una línea en resultado.txt."""
    registro.write(texto + "\n")
    registro.flush()


def esperar(ms):
    """Deja que QGIS dibuje la ventana antes de seguir."""
    bucle = QEventLoop()
    QTimer.singleShot(ms, bucle.quit)
    bucle.exec()


def captura(nombre, widget=None):
    """Espera a que QGIS dibuje y guarda una captura de la ventana (o del widget indicado)."""
    esperar(1200)
    (widget or iface.mainWindow()).grab().save(os.path.join(SALIDA, nombre + ".png"))


def paso(nombre):
    """Decorador: ejecuta un paso de la prueba y anota OK o FALLO."""
    def decorar(funcion):
        """Ejecuta la función decorada y anota OK o FALLO con su detalle."""
        try:
            detalle = funcion()
            resultados.append(True)
            escribir(f"OK     {nombre}" + (f"  ->  {detalle}" if detalle else ""))
        except Exception as error:  # noqa: BLE001
            resultados.append(False)
            escribir(f"FALLO  {nombre}  ->  {error}")
            escribir(traceback.format_exc())
        return funcion
    return decorar


def mensajes_barra():
    """Textos de la barra de mensajes de QGIS, en la forma 'título: texto'."""
    textos = []
    for item in iface.messageBar().items():
        textos.append(f"{item.title()}: {item.text()}")
    return textos


def capa(nombre):
    """Devuelve la capa del proyecto que tiene ese nombre."""
    return QgsProject.instance().mapLayersByName(nombre)[0]


def correr():
    """Ejecuta los 10 pasos de la prueba en orden y al final cierra QGIS."""
    from sigtec.dialogo_login import DialogoLogin
    estado = {}

    @paso("1. Activar el plugin instalado desde el ZIP: aparece el botón TEC")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        updateAvailablePlugins()
        loadPlugin("sigtec")
        startPlugin("sigtec")
        QgsSettings().setValue("PythonPlugins/sigtec", True)  # que quede activo al abrir QGIS
        iface.mainWindow().showMaximized()
        accion = plugins["sigtec"].accion
        assert accion.isVisible() or accion.associatedWidgets(), "el botón no está en la ventana"
        captura("01_boton_tec")
        return accion.text()

    plugin = plugins["sigtec"]

    def ingresar(usuario, clave, nombre_captura):
        """Abre la ventana de ingreso, escribe usuario y clave, presiona Ingresar y devuelve la ventana."""
        dialogo = DialogoLogin(plugin.ingresar, iface.mainWindow())
        dialogo.show()
        esperar(500)
        dialogo.usuario.setText(usuario)
        dialogo.clave.setText(clave)
        captura(nombre_captura + "_antes", dialogo)
        dialogo.boton_ingresar.click()
        esperar(800)
        if dialogo.isVisible():
            captura(nombre_captura, dialogo)
        return dialogo

    @paso("2. Ingreso con clave mala: mensaje rojo y la ventana sigue abierta")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        dialogo = ingresar("sancarlos1", "mala", "02_clave_mala")
        texto = dialogo.mensaje.text()
        assert dialogo.isVisible() and "incorrectos" in texto, texto
        dialogo.close()
        return texto

    @paso("3. Ingreso con usuario inactivo: se rechaza")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        dialogo = ingresar("inactivo1", "tec2026", "03_inactivo")
        texto = dialogo.mensaje.text()
        assert dialogo.isVisible() and "inactivo" in texto, texto
        dialogo.close()
        return texto

    @paso("4. Ingreso correcto: se cierra, carga 8 capas en el grupo, mapa en el campus y mensaje verde")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        dialogo = ingresar("sancarlos1", "tec2026", "04_login_ok")
        assert not dialogo.isVisible(), dialogo.mensaje.text()
        raiz = QgsProject.instance().layerTreeRoot()
        grupo = raiz.children()[0]
        nombres = [h.name() for h in grupo.findLayers()]
        assert len(nombres) == 8 and all(capa(n).isValid() for n in nombres), nombres
        captura("04_capas_cargadas")  # espera 1.2 s: tiempo para el zoom propio de QGIS
        extension = iface.mapCanvas().extent()
        # Un campus mide unos 500 m. Si el mapa muestra kilómetros, no quedó acercado al campus
        assert extension.width() < 3000, f"el mapa no quedó en el campus (ancho {extension.width():.0f} m)"
        estado["extension_campus"] = extension
        barra = mensajes_barra()
        assert any("Bienvenido sancarlos1" in m for m in barra), barra
        return (f"grupo '{grupo.name()}' | mapa de {extension.width():.0f} x {extension.height():.0f} m "
                f"(escala 1:{iface.mapCanvas().scale():.0f}) | {barra[-1][:60]}...")

    @paso("5. Estilos aplicados y datos de los 5 campus en cada capa")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        tipos = {n: capa(n).renderer().type() for n in ["Edificios", "Puntos de interés", "Iluminación"]}
        assert tipos["Puntos de interés"] == "categorizedSymbol" and capa("Edificios").labelsEnabled(), tipos
        campus = {f["campus_id"] for f in capa("Edificios").getFeatures()}
        assert campus == {1, 2, 3, 4, 5}, campus
        iface.zoomFull()
        captura("05_cinco_campus")
        iface.mapCanvas().setExtent(estado["extension_campus"])
        iface.mapCanvas().refresh()
        return f"{tipos} | campus {sorted(campus)}"

    @paso("6. Tabla de atributos de Edificios con campus_id de los 5 campus")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        tabla = iface.showAttributeTable(capa("Edificios"))
        tabla.resize(1100, 520)
        captura("06_tabla_atributos", tabla)
        tabla.close()
        return f"{capa('Edificios').featureCount()} edificios"

    @paso("7. Editar un edificio PROPIO (Laboratorios, pisos = 5) y guardar")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        c = capa("Edificios")
        iface.setActiveLayer(c)
        objeto = next(c.getFeatures(QgsFeatureRequest().setFilterExpression("\"nombre\" = 'Laboratorios'")))
        estado["pisos_antes"] = objeto["pisos"]
        c.startEditing()
        c.changeAttributeValue(objeto.id(), c.fields().indexOf("pisos"), 5)
        assert c.commitChanges(), c.commitErrors()
        captura("07_edicion_propia")
        return f"objeto {objeto['id']}: pisos {estado['pisos_antes']} -> 5"

    @paso("8. Editar un edificio de CARTAGO (Biblioteca): se rechaza y el plugin muestra el mensaje")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        c = capa("Edificios")
        objeto = next(c.getFeatures(QgsFeatureRequest().setFilterExpression("\"nombre\" = 'Biblioteca'")))
        antes = len(iface.messageBar().items())
        c.startEditing()
        c.changeAttributeValue(objeto.id(), c.fields().indexOf("pisos"), 9)
        guardado = c.commitChanges()
        captura("08_edicion_rechazada")
        c.rollBack()
        assert not guardado, "QGIS guardó el cambio en Cartago"
        nuevos = mensajes_barra()[antes:] or mensajes_barra()
        assert any("pertenece al Campus Tecnológico Central Cartago" in m for m in nuevos), nuevos
        return [m for m in nuevos if "pertenece" in m][0][:140] + "..."

    @paso("9. Crear un punto de interés nuevo en San Carlos (soda)")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        c = capa("Puntos de interés")
        iface.setActiveLayer(c)
        c.startEditing()
        nuevo = QgsFeature(c.fields())
        nuevo["nombre"] = "Soda de prueba QGIS"
        nuevo["tipo"] = "soda"
        nuevo.setGeometry(QgsGeometry.fromPointXY(iface.mapCanvas().extent().center()))
        assert c.addFeature(nuevo)
        assert c.commitChanges(), c.commitErrors()
        creado = next(c.getFeatures(QgsFeatureRequest().setFilterExpression("\"nombre\" = 'Soda de prueba QGIS'")))
        assert creado["campus_id"] == 3 and 3_000_000 < creado["id"] < 4_000_000
        captura("09_punto_nuevo")
        return f"id {creado['id']}, campus_id {creado['campus_id']}"

    @paso("10. Entrar con cartago1: el grupo cambia (sin duplicar) y el punto de San Carlos se ve desde Cartago")
    def _():
        """Cuerpo de este paso de la prueba (su nombre está en el decorador)."""
        esperar(1500)  # tiempo para que la replicación llegue a Cartago
        dialogo = ingresar("cartago1", "tec2026", "10_login_cartago")
        assert not dialogo.isVisible(), dialogo.mensaje.text()
        grupos = [g.name() for g in QgsProject.instance().layerTreeRoot().children()]
        assert grupos == ["SIG-TEC - Campus Tecnológico Central Cartago"], grupos
        visto = [f for f in capa("Puntos de interés").getFeatures() if f["nombre"] == "Soda de prueba QGIS"]
        assert len(visto) == 1 and visto[0]["campus_id"] == 3, "el punto no llegó a Cartago"
        captura("10_desde_cartago")
        return f"grupo {grupos[0]} | punto {visto[0]['id']} visible desde Cartago"

    escribir(f"RESULTADO {resultados.count(True)} OK {resultados.count(False)} FALLO")
    escribir("FIN")
    registro.close()
    QgsProject.instance().clear()
    QgsProject.instance().setDirty(False)
    QTimer.singleShot(1000, iface.actionExit().trigger)


# Esperar a que la ventana de QGIS termine de abrir antes de empezar
QTimer.singleShot(4000, correr)
