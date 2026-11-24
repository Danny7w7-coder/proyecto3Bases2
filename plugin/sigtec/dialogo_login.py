"""
Ventana de autenticación del plugin: usuario, contraseña y botón Ingresar.
Se arma con código (sin archivo .ui) para que sea fácil de leer.

La ventana NO sabe nada de la base de datos: recibe una función "al_ingresar(usuario, clave)"
que hace el trabajo. Si esa función lanza ErrorSigTec, el mensaje se muestra en rojo.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QApplication, QDialog, QFormLayout, QHBoxLayout, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout)

from .logica import ErrorSigTec


class DialogoLogin(QDialog):
    def __init__(self, al_ingresar, padre=None):
        super().__init__(padre)
        self.al_ingresar = al_ingresar
        self.setWindowTitle("SIG-TEC - Ingreso")
        self.setMinimumWidth(340)

        titulo = QLabel("<b>SIG-TEC</b><br>Sistema de Información Geográfica de los campus del TEC")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.usuario = QLineEdit()
        self.usuario.setPlaceholderText("ej. sancarlos1")
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.EchoMode.Password)  # muestra puntos en lugar de la clave

        formulario = QFormLayout()
        formulario.addRow("Usuario:", self.usuario)
        formulario.addRow("Contraseña:", self.clave)

        self.mensaje = QLabel("")
        self.mensaje.setWordWrap(True)
        self.mensaje.setStyleSheet("color: #b00020;")

        self.boton_ingresar = QPushButton("Ingresar")
        self.boton_ingresar.setDefault(True)  # Enter = Ingresar
        self.boton_ingresar.clicked.connect(self.ingresar)
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)

        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(boton_cancelar)
        botones.addWidget(self.boton_ingresar)

        diseno = QVBoxLayout(self)
        diseno.addWidget(titulo)
        diseno.addLayout(formulario)
        diseno.addWidget(self.mensaje)
        diseno.addLayout(botones)

    def ingresar(self):
        """Botón Ingresar: llama a al_ingresar. Si funciona cierra la ventana, si no muestra el error."""
        self.mensaje.setText("Conectando...")
        self.boton_ingresar.setEnabled(False)
        QApplication.processEvents()  # para que se vea "Conectando..." antes de esperar
        try:
            self.al_ingresar(self.usuario.text().strip(), self.clave.text())
            self.accept()
        except ErrorSigTec as error:
            self.mensaje.setText(str(error))
            self.clave.clear()
            self.clave.setFocus()
        finally:
            self.boton_ingresar.setEnabled(True)
