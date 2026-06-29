import sys
import os
import subprocess
import minecraft_launcher_lib as mll
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QLineEdit,
                             QComboBox, QProgressBar, QDialog, QSpinBox,
                             QGraphicsDropShadowEffect, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QPropertyAnimation
from PyQt6.QtGui import QColor, QIcon

PURPLE = "#8A2BE2"


class InstallWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, version, path):
        super().__init__()
        self.version = version
        self.path = path

    def run(self):
        def update_p(v):
            self.progress.emit(int(v))

        def update_s(t):
            self.status.emit(t)

        callback = {"setStatus": update_s, "setProgress": update_p, "setMax": lambda v: None}
        try:
            mll.install.install_minecraft_version(self.version, self.path, callback=callback)
        except Exception as e:
            self.status.emit(f"ОШИБКА: {e}")
        self.finished.emit()


class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setFixedSize(340, 380)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"background: #0A0A0A; color: white; border: 2px solid {PURPLE}; border-radius: 15px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(10)

        layout.addWidget(QLabel("ВЫДЕЛЕНИЕ ОЗУ (ГБ):", alignment=Qt.AlignmentFlag.AlignCenter))
        self.ram = QSpinBox()
        self.ram.setRange(2, 32)
        self.ram.setValue(current_settings["ram"])
        self.ram.setStyleSheet(
            f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 8px; border-radius: 5px;")
        layout.addWidget(self.ram)

        layout.addWidget(QLabel("ОТОБРАЖЕНИЕ ВЕРСИЙ:", alignment=Qt.AlignmentFlag.AlignCenter))

        cb_style = f"""
            QCheckBox {{ color: white; font-size: 13px; font-weight: bold; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {PURPLE}; border-radius: 4px; background: #111; }}
            QCheckBox::indicator:checked {{ background: {PURPLE}; }}
        """

        self.cb_snapshots = QCheckBox("Снапшоты")
        self.cb_snapshots.setChecked(current_settings["snapshots"])
        self.cb_snapshots.setStyleSheet(cb_style)
        layout.addWidget(self.cb_snapshots)

        self.cb_forge = QCheckBox("Forge / Fabric (Моды)")
        self.cb_forge.setChecked(current_settings["forge"])
        self.cb_forge.setStyleSheet(cb_style)
        layout.addWidget(self.cb_forge)

        self.cb_old_releases = QCheckBox("Старые релизы (< 1.14)")
        self.cb_old_releases.setChecked(current_settings["old_releases"])
        self.cb_old_releases.setStyleSheet(cb_style)
        layout.addWidget(self.cb_old_releases)

        self.cb_beta = QCheckBox("Бета версии (Beta)")
        self.cb_beta.setChecked(current_settings["beta"])
        self.cb_beta.setStyleSheet(cb_style)
        layout.addWidget(self.cb_beta)

        self.cb_alpha = QCheckBox("Альфа версии (Alpha)")
        self.cb_alpha.setChecked(current_settings["alpha"])
        self.cb_alpha.setStyleSheet(cb_style)
        layout.addWidget(self.cb_alpha)

        btn = QPushButton("СОХРАНИТЬ")
        btn.setStyleSheet(
            f"QPushButton {{ background: {PURPLE}; font-weight: bold; padding: 10px; border-radius: 5px; margin-top: 10px; }} QPushButton:hover {{ background: #9A3BF2; }}")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    def get_settings(self):
        return {
            "ram": self.ram.value(),
            "snapshots": self.cb_snapshots.isChecked(),
            "forge": self.cb_forge.isChecked(),
            "old_releases": self.cb_old_releases.isChecked(),
            "beta": self.cb_beta.isChecked(),
            "alpha": self.cb_alpha.isChecked()
        }


class RmyatoLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.base_path = os.path.join(os.getenv('APPDATA'), '.rmlauncher')
        self.settings = {
            "ram": 4,
            "snapshots": False,
            "forge": True,
            "old_releases": False,
            "beta": False,
            "alpha": False
        }

        self.setWindowTitle("launcher rmyato")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(580, 780)
        self.setWindowIcon(QIcon("rmyatolauncher.ico"))

        self.init_ui()
        self.refresh_versions()
        self.fade_in()

    def init_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QVBoxLayout(self.central)

        self.content = QWidget()
        self.content.setStyleSheet(
            f"background: rgba(10, 10, 10, 240); border: 2px solid {PURPLE}; border-radius: 40px;")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(PURPLE))
        shadow.setOffset(0, 0)
        self.content.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self.content)
        self.main_layout.addWidget(self.content)

        top = QHBoxLayout()
        self.btn_set = QPushButton("SETTINGS")
        self.btn_set.setStyleSheet(
            "QPushButton { color: #888; border: none; font-weight: bold; background: transparent; } QPushButton:hover { color: white; }")
        self.btn_set.clicked.connect(self.open_settings)
        close = QPushButton("✕")
        close.setFixedSize(40, 40)
        close.setStyleSheet(
            "QPushButton { color: white; border: none; font-size: 20px; background: transparent; } QPushButton:hover { color: #FF4444; }")
        close.clicked.connect(self.close)
        top.addWidget(self.btn_set)
        top.addStretch()
        top.addWidget(close)
        self.layout.addLayout(top)

        self.title = QLabel("RMYATOLAUNCHER")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(
            f"color: {PURPLE}; font-size: 42px; font-weight: 900; border: none; letter-spacing: 2px;")
        self.layout.addWidget(self.title)

        self.nick = QLineEdit("none")
        self.nick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nick.setStyleSheet(
            f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 15px; border-radius: 15px; font-size: 18px;")
        self.layout.addWidget(self.nick)

        self.v_box = QComboBox()
        self.v_box.setStyleSheet(f"""
            QComboBox {{ 
                background: #111; 
                color: {PURPLE}; 
                border: 1px solid {PURPLE}; 
                padding: 12px; 
                border-radius: 10px; 
                font-weight: bold;
            }}
            QComboBox QAbstractItemView {{ 
                background: #111; 
                color: {PURPLE}; 
                selection-background-color: {PURPLE}; 
                selection-color: white;
            }}
        """)
        self.v_box.currentIndexChanged.connect(self.check_status)
        layout_box = QHBoxLayout()
        layout_box.addWidget(self.v_box)
        self.layout.addLayout(layout_box)

        self.st_label = QLabel("ПРОВЕРКА ВЕРСИЙ...")
        self.st_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.st_label.setStyleSheet("color: #999; font-size: 12px; border: none; font-weight: bold;")
        self.layout.addWidget(self.st_label)

        self.pb = QProgressBar()
        self.pb.setFixedHeight(8)
        self.pb.setStyleSheet(
            f"QProgressBar {{ background: #222; border-radius: 4px; border: none; }} QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PURPLE}, stop:1 #FF00FF); border-radius: 4px; }}")
        self.pb.hide()
        self.layout.addWidget(self.pb)

        self.layout.addStretch()

        self.btn_main = QPushButton("ИГРАТЬ")
        self.btn_main.setFixedHeight(90)
        self.btn_main.setStyleSheet(f"""
            QPushButton {{ 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PURPLE}, stop:1 #6A1B9A); 
                color: white; 
                font-size: 28px; 
                font-weight: bold; 
                border-radius: 25px; 
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9A3BF2, stop:1 #7A2BAA); 
            }}
            QPushButton:pressed {{
                background: #5A0B8A;
            }}
        """)
        self.btn_main.clicked.connect(self.handle_click)
        self.layout.addWidget(self.btn_main)

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self.refresh_versions()

    def is_old_release(self, v_id):
        try:
            parts = [int(x) for x in v_id.split('.')]
            if len(parts) >= 2 and parts[0] == 1 and parts[1] < 14:
                return True
        except:
            pass
        return False

    def refresh_versions(self):
        self.v_box.clear()
        try:
            all_v = mll.utils.get_version_list()

            allowed_types = ["release"]
            if self.settings["snapshots"]:
                allowed_types.append("snapshot")
            if self.settings["beta"]:
                allowed_types.append("old_beta")
            if self.settings["alpha"]:
                allowed_types.append("old_alpha")

            releases = []
            for v in all_v:
                v_type = v['type']
                v_id = v['id']
                if v_type in allowed_types:
                    if v_type == "release" and not self.settings["old_releases"]:
                        if self.is_old_release(v_id):
                            continue
                    releases.append(v_id)

            installed = [v['id'] for v in mll.utils.get_installed_versions(self.base_path)]
            filtered_installed = []
            for v_id in installed:
                is_modded = any(x in v_id.lower() for x in ["forge", "fabric", "quilt", "liteloader"])
                if is_modded:
                    if self.settings["forge"]:
                        filtered_installed.append(v_id)
                else:
                    if "w" in v_id or "pre" in v_id or "rc" in v_id:
                        if not self.settings["snapshots"]: continue
                    elif v_id.startswith("b1."):
                        if not self.settings["beta"]: continue
                    elif v_id.startswith("a1."):
                        if not self.settings["alpha"]: continue
                    elif self.is_old_release(v_id):
                        if not self.settings["old_releases"]: continue
                    filtered_installed.append(v_id)

            final_list = sorted(list(set(filtered_installed + releases)), reverse=True)
            self.v_box.addItems(final_list)
            self.check_status()
        except:
            self.st_label.setText("ОШИБКА ОБНОВЛЕНИЯ")

    def check_status(self):
        v = self.v_box.currentText()
        if not v: return
        v_path = os.path.join(self.base_path, "versions", v)
        if os.path.exists(v_path):
            self.btn_main.setText("ИГРАТЬ")
            self.st_label.setText("ГОТОВ К ЗАПУСКУ 🚀")
        else:
            self.btn_main.setText("СКАЧАТЬ")
            self.st_label.setText("НУЖНО СКАЧАТЬ ВЕРСИЮ 📦")

    def handle_click(self):
        v = self.v_box.currentText()
        if not os.path.exists(os.path.join(self.base_path, "versions", v)):
            self.pb.show()
            self.worker = InstallWorker(v, self.base_path)
            self.worker.progress.connect(self.pb.setValue)
            self.worker.status.connect(self.st_label.setText)
            self.worker.finished.connect(self.on_done)
            self.worker.start()
        else:
            self.launch_game()

    def on_done(self):
        self.pb.hide()
        self.check_status()

    def launch_game(self):
        v = self.v_box.currentText()
        options = {"username": self.nick.text(), "jvmArguments": [f"-Xmx{self.settings['ram']}G"]}
        try:
            cmd = mll.command.get_minecraft_command(v, self.base_path, options)
            subprocess.Popen(cmd, creationflags=0x08000000)
            self.fade_out()
        except:
            self.st_label.setText("ОШИБКА ЗАПУСКА")

    def fade_in(self):
        self.setWindowOpacity(0.0)
        self.anim_in = QPropertyAnimation(self, b"windowOpacity")
        self.anim_in.setDuration(600)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.start()

    def fade_out(self):
        self.anim_out = QPropertyAnimation(self, b"windowOpacity")
        self.anim_out.setDuration(400)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.finished.connect(self.close)
        self.anim_out.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self.old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if hasattr(self, "old_pos"):
            delta = QPoint(e.globalPosition().toPoint() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = e.globalPosition().toPoint()


if __name__ == "__main__":
    if os.name == 'nt':
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("rmyato.launcher.1.0")

    app = QApplication(sys.argv)
    w = RmyatoLauncher()
    w.show()
    sys.exit(app.exec())