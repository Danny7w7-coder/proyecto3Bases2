"""
Clase principal del plugin SIG-TEC.

Flujo al presionar el botón "SIG-TEC":
  1. Se abre la ventana de login.
  2. Se llama a autenticar() en el nodo CENTRAL.
  3. Con el campus del usuario, se conecta a SU nodo y lee los estilos vigentes.
  4. Agrega las 8 vistas al proyecto, con su estilo, y acerca el mapa al campus.
  5. Si la base rechaza una edición, muestra el mensaje en la barra de QGIS.
"""
import os

from qgis.core import Qgis
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from . import capas as modulo_capas
from . import logica
from .dialogo_login import DialogoLogin

TITULO = "SIG-TEC"


def crear_ejecutor(host, puerto, base, usuario, clave):
    """Usa psycopg2 si está disponible; si no, la conexión propia de QGIS."""
    if logica.psycopg2_disponible():
        return logica.ejecutor_psycopg2(host, puerto, base, usuario, clave)
    from .conexion_qgis import ejecutor_qgis
    return ejecutor_qgis(host, puerto, base, usuario, clave)


class SigTecPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.accion = None
        self.sesion = None  # datos del usuario que entró (resultado de autenticar)

    # --- QGIS llama a estos dos métodos al activar / desactivar el plugin ---
    def initGui(self):
        icono = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.accion = QAction(icono, "SIG-TEC: Ingresar", self.iface.mainWindow())
        self.accion.triggered.connect(self.abrir_login)
        self.iface.addToolBarIcon(self.accion)
        self.iface.addPluginToMenu(TITULO, self.accion)

    def unload(self):
        self.iface.removePluginMenu(TITULO, self.accion)
        self.iface.removeToolBarIcon(self.accion)

    # --- Login ---
    def abrir_login(self):
        dialogo = DialogoLogin(self.ingresar, self.iface.mainWindow())
        dialogo.exec()

    def ingresar(self, usuario, clave):
        """Hace todo el proceso de ingreso. Lanza ErrorSigTec si algo falla (lo muestra la ventana)."""
        config = logica.leer_config()
        central = config["central"]

        # 1-3. Autenticar en el central
        ejecutar_central = crear_ejecutor(central["host"], central["puerto"], central["base"],
                                          central["usuario"], central["clave"])
        datos = logica.autenticar(ejecutar_central, usuario, clave)

        # 4. Conectarse al nodo del campus: estilos y zona del campus
        ejecutar_nodo = crear_ejecutor(datos["host"], datos["puerto"], datos["base"],
                                       datos["usuario_conexion"], datos["clave_conexion"])
        estilos = logica.estilos_vigentes(ejecutar_nodo)
        extension = logica.extension_campus(ejecutar_nodo, datos["campus_id"])

        # 5. Agregar las capas al proyecto actual
        capas, problemas = modulo_capas.cargar_capas(datos, config["srid"], estilos, self.mostrar_error_edicion)
        if not capas:
            raise logica.ErrorSigTec("No se pudo cargar ninguna capa:\n" + "\n".join(problemas))

        rect = modulo_capas.rectangulo(extension)
        if rect:
            self.iface.mapCanvas().setExtent(rect)
            self.iface.mapCanvas().refresh()

        self.sesion = datos
        texto = (f"Bienvenido {datos['usuario']} ({datos['campus_nombre']}). "
                 f"Se cargaron {len(capas)} capas. Puede consultar todos los campus "
                 f"y editar solo los objetos de su campus.")
        self.iface.messageBar().pushMessage(TITULO, texto, level=Qgis.MessageLevel.Success, duration=8)
        if problemas:
            QMessageBox.warning(self.iface.mainWindow(), TITULO, "\n".join(problemas))

    # --- Errores de edición ---
    def mostrar_error_edicion(self, capa, mensaje):
        """La base rechazó un cambio (por ejemplo, un objeto de otro campus)."""
        self.iface.messageBar().pushMessage(
            f"{TITULO} - {capa}",
            f"{mensaje} Use 'Descartar ediciones' para deshacer el cambio rechazado.",
            level=Qgis.MessageLevel.Critical, duration=15)
