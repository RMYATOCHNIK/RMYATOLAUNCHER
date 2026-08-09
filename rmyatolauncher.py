import sys
import os
import json
import zipfile
import urllib.request
import urllib.parse
import subprocess
import minecraft_launcher_lib as mll
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QLineEdit,
                             QComboBox, QProgressBar, QDialog, QSpinBox,
                             QGraphicsDropShadowEffect, QCheckBox, QTextEdit,
                             QFileDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QIcon

PURPLE = "#8A2BE2"

JAVA_URLS = {
    8: "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u412-b08/OpenJDK8U-jre_x64_windows_hotspot_8u412b08.zip",
    17: "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.11%2B9/OpenJDK17U-jre_x64_windows_hotspot_17.0.11_9.zip",
    21: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.3%2B9/OpenJDK21U-jre_x64_windows_hotspot_21.0.3_9.zip",
    25: "https://download.java.net/java/GA/jdk25/0/GPL/openjdk-25_windows-x64_bin.zip"
}

LANGUAGES = {
    "Русский": "ru_ru",
    "English (US)": "en_us",
    "Українська": "uk_ua",
    "Қазақша": "kk_kz"
}


def get_required_java_version(mc_version: str) -> int:
    try:
        clean_ver = mc_version.split('-')[0]
        parts = [int(x) for x in clean_ver.split('.') if x.isdigit()]
        minor = parts[1] if len(parts) > 1 else 0
        patch = parts[2] if len(parts) > 2 else 0

        if minor < 17:
            return 8
        elif minor < 20 or (minor == 20 and patch <= 4):
            return 17
        elif minor < 25:
            return 21
        else:
            return 25
    except Exception:
        return 21


class JavaDownloaderWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

    def __init__(self, java_version, base_path):
        super().__init__()
        self.java_version = java_version
        self.base_path = base_path

    def run(self):
        java_dir = os.path.join(self.base_path, "runtimes", f"java-{self.java_version}")

        if os.path.exists(java_dir):
            for root, _, files in os.walk(java_dir):
                if "javaw.exe" in files:
                    self.finished_signal.emit(os.path.join(root, "javaw.exe"))
                    return
                if "java.exe" in files:
                    self.finished_signal.emit(os.path.join(root, "java.exe"))
                    return

        url = JAVA_URLS.get(self.java_version)
        if not url:
            self.status.emit(f"Ошибка: нет URL для Java {self.java_version}")
            self.finished_signal.emit("java")
            return

        try:
            os.makedirs(java_dir, exist_ok=True)
            zip_path = os.path.join(java_dir, f"java_{self.java_version}.zip")

            self.status.emit(f"Загрузка Java {self.java_version}...")

            def progress_hook(count, block_size, total_size):
                if total_size > 0:
                    percent = int(count * block_size * 100 / total_size)
                    self.progress.emit(min(percent, 100))

            urllib.request.urlretrieve(url, zip_path, progress_hook)

            self.status.emit(f"Распаковка Java {self.java_version}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(java_dir)

            if os.path.exists(zip_path):
                os.remove(zip_path)

            for root, _, files in os.walk(java_dir):
                if "javaw.exe" in files:
                    self.finished_signal.emit(os.path.join(root, "javaw.exe"))
                    return
                if "java.exe" in files:
                    self.finished_signal.emit(os.path.join(root, "java.exe"))
                    return

        except Exception as e:
            self.status.emit(f"Ошибка скачивания Java: {e}")

        self.finished_signal.emit("java")


class CrashDialog(QDialog):
    def __init__(self, log_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ошибка запуска Minecraft")
        self.resize(600, 400)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"background: #0A0A0A; color: white; border: 2px solid {PURPLE}; border-radius: 15px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("ИГРА ВЫЛЕТЕЛА C ОШИБКОЙ")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FF4444; font-size: 18px; font-weight: bold; border: none;")
        layout.addWidget(title)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setPlainText(log_text)
        self.text_area.setStyleSheet(f"""
            QTextEdit {{
                background: #111;
                color: #FF6666;
                font-family: Consolas, monospace;
                font-size: 12px;
                border: 1px solid {PURPLE};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        layout.addWidget(self.text_area)

        btn_close = QPushButton("ЗАКРЫТЬ")
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {PURPLE};
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 8px;
            }}
            QPushButton:hover {{ background: #9A3BF2; }}
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class LaunchWorker(QThread):
    crash_signal = pyqtSignal(str)
    started_signal = pyqtSignal()
    finished_signal = pyqtSignal()

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd

    def run(self):
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=creation_flags
            )

            self.started_signal.emit()
            logs = []

            for line in process.stdout:
                logs.append(line)
                if len(logs) > 500:
                    logs.pop(0)

            process.wait()

            if process.returncode != 0:
                full_log = "".join(logs)
                if not full_log.strip():
                    full_log = f"Игра завершилась с кодом ошибки: {process.returncode}"
                self.crash_signal.emit(full_log)

        except Exception as e:
            self.crash_signal.emit(f"Исключение при попытке запуска:\n{e}")
        finally:
            self.finished_signal.emit()


class InstallWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, version, path, install_type="vanilla"):
        super().__init__()
        self.version = version
        self.path = path
        self.install_type = install_type

    def run(self):
        callback = {
            "setStatus": lambda t: self.status.emit(str(t)),
            "setProgress": lambda v: self.progress.emit(int(v)),
            "setMax": lambda v: None
        }
        try:
            if self.install_type == "vanilla":
                mll.install.install_minecraft_version(self.version, self.path, callback=callback)
            elif self.install_type == "fabric":
                self.status.emit(f"Установка Fabric {self.version}...")
                mll.fabric.install_fabric(self.version, self.path, callback=callback)
            elif self.install_type == "forge":
                self.status.emit(f"Установка Forge {self.version}...")
                forge_ver = mll.forge.find_forge_version(self.version)
                if forge_ver:
                    mll.forge.install_forge_version(forge_ver, self.path, callback=callback)
                else:
                    self.status.emit("Не удалось найти инсталлятор Forge")
        except Exception as e:
            self.status.emit(f"ОШИБКА: {e}")

        self.finished.emit()


class ModInstallerDialog(QDialog):
    def __init__(self, mc_version, loader_type, game_path, parent=None):
        super().__init__(parent)
        self.mc_version = mc_version
        self.loader_type = loader_type.lower()
        self.game_path = game_path

        self.setWindowTitle(f"Моды для {mc_version} ({self.loader_type.capitalize()})")
        self.setFixedSize(540, 480)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"background: #0A0A0A; color: white; border: 2px solid {PURPLE}; border-radius: 15px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        top_layout = QHBoxLayout()
        title = QLabel(f"МЕНЕДЖЕР МОДОВ [{self.loader_type.upper()}] - MC {self.mc_version}")
        title.setStyleSheet(f"color: {PURPLE}; font-weight: bold; font-size: 13px; border: none;")
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("QPushButton { color: white; border: none; font-size: 16px; background: transparent; } QPushButton:hover { color: #FF4444; }")
        btn_close.clicked.connect(self.accept)
        top_layout.addWidget(title)
        top_layout.addStretch()
        top_layout.addWidget(btn_close)
        layout.addLayout(top_layout)

        search_layout = QHBoxLayout()
        self.source_box = QComboBox()
        self.source_box.addItems(["CurseForge", "Modrinth"])
        self.source_box.setStyleSheet(f"background: #111; color: {PURPLE}; border: 1px solid {PURPLE}; padding: 6px; border-radius: 5px; font-weight: bold;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Введите название мода...")
        self.search_input.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 8px; border-radius: 5px;")
        self.search_input.returnPressed.connect(self.search_mods)

        btn_search = QPushButton("Искать")
        btn_search.setStyleSheet(f"background: {PURPLE}; color: white; font-weight: bold; padding: 8px 15px; border-radius: 5px;")
        btn_search.clicked.connect(self.search_mods)

        search_layout.addWidget(self.source_box)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_search)
        layout.addLayout(search_layout)

        self.status_label = QLabel("Выберите площадку и введите название")
        self.status_label.setStyleSheet("color: #888; border: none; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.mods_list = QTextEdit()
        self.mods_list.setReadOnly(True)
        self.mods_list.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; border-radius: 8px; padding: 10px;")
        layout.addWidget(self.mods_list)

        self.btn_download = QPushButton("СКАЧАТЬ И УСТАНОВИТЬ В /MODS")
        self.btn_download.setEnabled(False)
        self.btn_download.setStyleSheet(f"QPushButton {{ background: {PURPLE}; color: white; font-weight: bold; padding: 10px; border-radius: 8px; }} QPushButton:disabled {{ background: #333; color: #666; }}")
        self.btn_download.clicked.connect(self.download_selected_mod)
        layout.addWidget(self.btn_download)

        self.found_file_url = None
        self.found_filename = None

    def search_mods(self):
        query = self.search_input.text().strip()
        if not query:
            return

        source = self.source_box.currentText()
        self.status_label.setText(f"Поиск на {source}...")
        self.btn_download.setEnabled(False)
        self.found_file_url = None

        if source == "Modrinth":
            self.search_modrinth(query)
        else:
            self.search_curseforge(query)

    def search_modrinth(self, query):
        search_url = f"https://api.modrinth.com/v2/search?query={urllib.parse.quote(query)}&facets=[[\"categories:{self.loader_type}\"],[\"versions:{self.mc_version}\"],[\"project_type:mod\"]]"
        try:
            req = urllib.request.Request(search_url, headers={'User-Agent': 'RmyatoLauncher/1.0'})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            hits = data.get('hits', [])
            if not hits:
                self.status_label.setText("Моды не найдены.")
                return

            top_hit = hits[0]
            project_id = top_hit['project_id']
            title = top_hit['title']
            desc = top_hit['description']

            versions_url = f"https://api.modrinth.com/v2/project/{project_id}/version?loaders=[\"{self.loader_type}\"]&game_versions=[\"{self.mc_version}\"]"
            req_v = urllib.request.Request(versions_url, headers={'User-Agent': 'RmyatoLauncher/1.0'})

            with urllib.request.urlopen(req_v) as resp_v:
                v_data = json.loads(resp_v.read().decode())

            if not v_data:
                self.status_label.setText("Подходящих файлов под версию нет.")
                return

            file_info = v_data[0]['files'][0]
            self.found_file_url = file_info['url']
            self.found_filename = file_info['filename']

            self.mods_list.setPlainText(f"[Modrinth] Название: {title}\n\nОписание: {desc}\n\nИмя файла: {self.found_filename}")
            self.status_label.setText("Файл найден! Можно скачивать.")
            self.btn_download.setEnabled(True)

        except Exception as e:
            self.status_label.setText(f"Ошибка запроса: {e}")

    def search_curseforge(self, query):
        loader_id = 1 if self.loader_type == "forge" else 4
        search_url = f"https://api.curse.tools/v1/cf/mods/search?gameId=432&searchFilter={urllib.parse.quote(query)}&modLoaderType={loader_id}&gameVersion={self.mc_version}"

        try:
            req = urllib.request.Request(search_url, headers={'User-Agent': 'RmyatoLauncher/1.0'})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            data_list = data.get('data', [])
            if not data_list:
                self.status_label.setText("Моды не найдены.")
                return

            top_hit = data_list[0]
            mod_id = top_hit['id']
            title = top_hit['name']
            desc = top_hit.get('summary', '')

            files_url = f"https://api.curse.tools/v1/cf/mods/{mod_id}/files?gameVersion={self.mc_version}&modLoaderType={loader_id}"
            req_f = urllib.request.Request(files_url, headers={'User-Agent': 'RmyatoLauncher/1.0'})

            with urllib.request.urlopen(req_f) as resp_f:
                f_data = json.loads(resp_f.read().decode())

            f_list = f_data.get('data', [])
            if not f_list:
                self.status_label.setText("Файл не найден.")
                return

            file_info = f_list[0]
            self.found_file_url = file_info.get('downloadUrl')
            self.found_filename = file_info.get('fileName')

            self.mods_list.setPlainText(f"[CurseForge] Название: {title}\n\nОписание: {desc}\n\nИмя файла: {self.found_filename}")
            self.status_label.setText("Файл найден! Можно скачивать.")
            self.btn_download.setEnabled(True)

        except Exception as e:
            self.status_label.setText(f"Ошибка: {e}")

    def download_selected_mod(self):
        if not self.found_file_url:
            return

        mods_dir = os.path.join(self.game_path, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        save_path = os.path.join(mods_dir, self.found_filename)

        try:
            self.status_label.setText("Загрузка мода...")
            req = urllib.request.Request(self.found_file_url, headers={'User-Agent': 'RmyatoLauncher/1.0'})
            with urllib.request.urlopen(req) as response, open(save_path, 'wb') as out_file:
                out_file.write(response.read())

            self.status_label.setText(f"Успешно установлен в mods/{self.found_filename}!")
            self.btn_download.setEnabled(False)
        except Exception as e:
            self.status_label.setText(f"Ошибка: {e}")


class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 520)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"background: #0A0A0A; color: white; border: 2px solid {PURPLE}; border-radius: 15px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(8)

        layout.addWidget(QLabel("ВЫДЕЛЕНИЕ ОЗУ (ГБ):", alignment=Qt.AlignmentFlag.AlignCenter))
        self.ram = QSpinBox()
        self.ram.setRange(2, 32)
        self.ram.setValue(current_settings.get("ram", 4))
        self.ram.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.ram)

        layout.addWidget(QLabel("ЯЗЫК ИГРЫ:", alignment=Qt.AlignmentFlag.AlignCenter))
        self.lang_box = QComboBox()
        self.lang_box.addItems(list(LANGUAGES.keys()))
        self.lang_box.setCurrentText(current_settings.get("lang_name", "Русский"))
        self.lang_box.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.lang_box)

        layout.addWidget(QLabel("ВЕРСИЯ JAVA:", alignment=Qt.AlignmentFlag.AlignCenter))
        self.java_mode = QComboBox()
        self.java_mode.addItems(["Автоматически", "Java 8", "Java 17", "Java 21", "Java 25", "Свой путь к java.exe"])
        self.java_mode.setCurrentText(current_settings.get("java_mode", "Автоматически"))
        self.java_mode.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 6px; border-radius: 5px;")
        self.java_mode.currentIndexChanged.connect(self.toggle_custom_java)
        layout.addWidget(self.java_mode)

        self.custom_java_layout = QHBoxLayout()
        self.custom_java_path = QLineEdit(current_settings.get("custom_java_path", ""))
        self.custom_java_path.setPlaceholderText("Путь к java.exe...")
        self.custom_java_path.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 6px; border-radius: 5px;")
        self.btn_browse_java = QPushButton("...")
        self.btn_browse_java.setFixedWidth(40)
        self.btn_browse_java.setStyleSheet(f"background: {PURPLE}; color: white; font-weight: bold; border-radius: 5px; padding: 6px;")
        self.btn_browse_java.clicked.connect(self.browse_java)
        self.custom_java_layout.addWidget(self.custom_java_path)
        self.custom_java_layout.addWidget(self.btn_browse_java)
        layout.addLayout(self.custom_java_layout)

        layout.addWidget(QLabel("ОТОБРАЖЕНИЕ ВЕРСИЙ:", alignment=Qt.AlignmentFlag.AlignCenter))

        cb_style = f"""
            QCheckBox {{ color: white; font-size: 12px; font-weight: bold; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {PURPLE}; border-radius: 3px; background: #111; }}
            QCheckBox::indicator:checked {{ background: {PURPLE}; }}
        """

        self.cb_snapshots = QCheckBox("Снапшоты")
        self.cb_snapshots.setChecked(current_settings.get("snapshots", False))
        self.cb_snapshots.setStyleSheet(cb_style)
        layout.addWidget(self.cb_snapshots)

        self.cb_old_releases = QCheckBox("Старые релизы (< 1.14)")
        self.cb_old_releases.setChecked(current_settings.get("old_releases", True))
        self.cb_old_releases.setStyleSheet(cb_style)
        layout.addWidget(self.cb_old_releases)

        btn = QPushButton("СОХРАНИТЬ")
        btn.setStyleSheet(f"QPushButton {{ background: {PURPLE}; font-weight: bold; padding: 10px; border-radius: 5px; margin-top: 10px; }} QPushButton:hover {{ background: #9A3BF2; }}")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

        self.toggle_custom_java()

    def toggle_custom_java(self):
        is_custom = self.java_mode.currentText() == "Свой путь к java.exe"
        self.custom_java_path.setVisible(is_custom)
        self.btn_browse_java.setVisible(is_custom)

    def browse_java(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите java.exe или javaw.exe", "", "Executable (*.exe)")
        if file_path:
            self.custom_java_path.setText(file_path)

    def get_settings(self):
        return {
            "ram": self.ram.value(),
            "lang_name": self.lang_box.currentText(),
            "lang_code": LANGUAGES.get(self.lang_box.currentText(), "ru_ru"),
            "java_mode": self.java_mode.currentText(),
            "custom_java_path": self.custom_java_path.text().strip(),
            "snapshots": self.cb_snapshots.isChecked(),
            "old_releases": self.cb_old_releases.isChecked()
        }


class RmyatoLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        appdata_dir = os.getenv('APPDATA') or os.path.expanduser('~')
        self.base_dir = os.path.join(appdata_dir, 'rmyatochnik', '.rmlauncher')
        self.save_dir = os.path.join(self.base_dir, 'launcher', 'save')
        self.base_path = os.path.join(self.base_dir, 'game')
        self.config_file = os.path.join(self.save_dir, 'config.json')

        self.drag_position = QPoint()

        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "versions"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "mods"), exist_ok=True)

        self.settings = {
            "username": "Player",
            "ram": 4,
            "lang_name": "Русский",
            "lang_code": "ru_ru",
            "java_mode": "Автоматически",
            "custom_java_path": "",
            "snapshots": False,
            "old_releases": True,
            "loader": "Vanilla"
        }

        self.load_config()

        self.setWindowTitle("launcher rmyato")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(580, 780)

        if os.path.exists("rmyatolauncher.ico"):
            self.setWindowIcon(QIcon("rmyatolauncher.ico"))

        self.init_ui()
        self.refresh_versions()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"Ошибка конфигурации: {e}")

    def save_config(self):
        try:
            if hasattr(self, 'nick'):
                self.settings["username"] = self.nick.text().strip() or "Player"
            if hasattr(self, 'type_box'):
                self.settings["loader"] = self.type_box.currentText()
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения: {e}")

    def init_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QVBoxLayout(self.central)

        self.content = QWidget()
        self.content.setStyleSheet(f"background: rgba(10, 10, 10, 240); border: 2px solid {PURPLE}; border-radius: 40px;")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(PURPLE))
        shadow.setOffset(0, 0)
        self.content.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self.content)
        self.main_layout.addWidget(self.content)

        top = QHBoxLayout()
        self.btn_set = QPushButton("SETTINGS")
        self.btn_set.setStyleSheet("QPushButton { color: #888; border: none; font-weight: bold; background: transparent; } QPushButton:hover { color: white; }")
        self.btn_set.clicked.connect(self.open_settings)

        self.btn_mods = QPushButton("MODS")
        self.btn_mods.setStyleSheet("QPushButton { color: #888; border: none; font-weight: bold; background: transparent; margin-left: 10px; } QPushButton:hover { color: white; }")
        self.btn_mods.clicked.connect(self.open_mods_installer)

        close = QPushButton("✕")
        close.setFixedSize(40, 40)
        close.setStyleSheet("QPushButton { color: white; border: none; font-size: 20px; background: transparent; } QPushButton:hover { color: #FF4444; }")
        close.clicked.connect(self.close)

        top.addWidget(self.btn_set)
        top.addWidget(self.btn_mods)
        top.addStretch()
        top.addWidget(close)
        self.layout.addLayout(top)

        self.title = QLabel("RMYATOLAUNCHER")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(f"color: {PURPLE}; font-size: 42px; font-weight: 900; border: none; letter-spacing: 2px;")
        self.layout.addWidget(self.title)

        self.nick = QLineEdit(self.settings.get("username", "Player"))
        self.nick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nick.setStyleSheet(f"background: #111; color: white; border: 1px solid {PURPLE}; padding: 15px; border-radius: 15px; font-size: 18px;")
        self.nick.textChanged.connect(self.save_config)
        self.layout.addWidget(self.nick)

        layout_box = QHBoxLayout()

        self.type_box = QComboBox()
        self.type_box.addItems(["Vanilla", "Forge", "Fabric"])
        self.type_box.setCurrentText(self.settings.get("loader", "Vanilla"))
        self.type_box.setFixedWidth(120)
        self.type_box.setStyleSheet(f"""
            QComboBox {{ 
                background: #111; 
                color: white; 
                border: 1px solid {PURPLE}; 
                padding: 12px; 
                border-radius: 10px; 
                font-weight: bold;
            }}
            QComboBox QAbstractItemView {{ 
                background: #111; 
                color: white; 
                selection-background-color: {PURPLE}; 
            }}
        """)
        self.type_box.currentIndexChanged.connect(self.on_loader_changed)

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

        layout_box.addWidget(self.type_box)
        layout_box.addWidget(self.v_box)
        self.layout.addLayout(layout_box)

        self.st_label = QLabel("ЗАГРУЗКА СПИСКА ВЕРСИЙ...")
        self.st_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.st_label.setStyleSheet("color: #999; font-size: 12px; border: none; font-weight: bold;")
        self.layout.addWidget(self.st_label)

        self.pb = QProgressBar()
        self.pb.setFixedHeight(8)
        self.pb.setStyleSheet(f"QProgressBar {{ background: #222; border-radius: 4px; border: none; }} QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PURPLE}, stop:1 #FF00FF); border-radius: 4px; }}")
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

    def on_loader_changed(self):
        self.save_config()
        self.refresh_versions()

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            updated = dialog.get_settings()
            self.settings.update(updated)
            self.save_config()
            self.refresh_versions()

    def open_mods_installer(self):
        v = self.v_box.currentText()
        loader = self.type_box.currentText().lower()

        if loader == "vanilla":
            self.st_label.setText("ДЛЯ МОДОВ ВЫБЕРИТЕ FORGE ИЛИ FABRIC В МЕНЮ ВЕРСИЙ!")
            return

        mc_ver = v.split('-')[0].strip()
        dialog = ModInstallerDialog(mc_ver, loader, self.base_path, self)
        dialog.exec()

    def refresh_versions(self):
        self.st_label.setText("ПОЛУЧЕНИЕ СПИСКА ВЕРСИЙ...")
        self.v_box.blockSignals(True)
        self.v_box.clear()

        loader = self.type_box.currentText()

        try:
            versions = []
            if loader == "Vanilla":
                all_v = mll.utils.get_version_list()
                allowed = ["release"]
                if self.settings["snapshots"]:
                    allowed.append("snapshot")
                for v in all_v:
                    if v.get("type") in allowed:
                        versions.append(v.get("id"))
            elif loader == "Fabric":
                try:
                    all_fabric = mll.fabric.get_all_game_versions()
                    versions = [v["version"] for v in all_fabric if v.get("stable", True)]
                except Exception:
                    versions = [v.get("id") for v in mll.utils.get_version_list() if v.get("type") == "release"]
            elif loader == "Forge":
                try:
                    all_forge = mll.forge.list_forge_versions()
                    versions = sorted(list(set([v.split('-')[0] for v in all_forge if '-' in v])), reverse=True)
                except Exception:
                    versions = [v.get("id") for v in mll.utils.get_version_list() if v.get("type") == "release"]

            self.v_box.addItems(versions)

        except Exception as e:
            self.st_label.setText(f"Ошибка списков: {e}")

        self.v_box.blockSignals(False)
        self.check_status()

    def check_status(self):
        v = self.v_box.currentText()
        if not v:
            self.btn_main.setText("НЕТ ВЕРСИИ")
            self.st_label.setText("Версии не найдены")
            return

        loader = self.type_box.currentText()
        installed_versions = [x["id"] for x in mll.utils.get_installed_versions(self.base_path)]

        target_id = v
        if loader == "Fabric":
            target_id = f"fabric-loader-{v}"
        elif loader == "Forge":
            target_id = f"{v}-forge"

        is_installed = any(target_id in x or v in x for x in installed_versions)

        if is_installed:
            self.btn_main.setText("ИГРАТЬ")
            self.st_label.setText(f"Версия {loader} {v} готова")
        else:
            self.btn_main.setText("СКАЧАТЬ")
            self.st_label.setText(f"Требуется установка {loader} {v}")

    def handle_click(self):
        v = self.v_box.currentText()
        if not v:
            return

        loader = self.type_box.currentText()
        installed_versions = [x["id"] for x in mll.utils.get_installed_versions(self.base_path)]

        launch_ver = v
        if loader == "Fabric":
            for installed in installed_versions:
                if "fabric" in installed.lower() and v in installed:
                    launch_ver = installed
                    break
        elif loader == "Forge":
            for installed in installed_versions:
                if "forge" in installed.lower() and v in installed:
                    launch_ver = installed
                    break

        if launch_ver in installed_versions or (loader == "Vanilla" and v in installed_versions):
            self.prepare_and_launch(launch_ver)
        else:
            self.install_version(v, loader.lower())

    def install_version(self, v, loader_type):
        self.btn_main.setEnabled(False)
        self.pb.show()
        self.pb.setValue(0)

        self.worker = InstallWorker(v, self.base_path, loader_type)
        self.worker.progress.connect(self.pb.setValue)
        self.worker.status.connect(self.st_label.setText)
        self.worker.finished.connect(self.on_install_finished)
        self.worker.start()

    def on_install_finished(self):
        self.pb.hide()
        self.btn_main.setEnabled(True)
        self.check_status()

    def prepare_and_launch(self, v):
        java_mode = self.settings.get("java_mode", "Автоматически")

        if java_mode == "Свой путь к java.exe":
            custom_path = self.settings.get("custom_java_path", "")
            if os.path.exists(custom_path):
                self.launch_game(v, custom_path)
            else:
                self.st_label.setText("Путь к Java не существует!")
            return

        if java_mode.startswith("Java "):
            req_ver = int(java_mode.split()[1])
        else:
            req_ver = get_required_java_version(v)

        java_dir = os.path.join(self.base_path, "runtimes", f"java-{req_ver}")
        java_exe = None

        if os.path.exists(java_dir):
            for root, _, files in os.walk(java_dir):
                if "javaw.exe" in files:
                    java_exe = os.path.join(root, "javaw.exe")
                    break
                if "java.exe" in files:
                    java_exe = os.path.join(root, "java.exe")
                    break

        if java_exe and os.path.exists(java_exe):
            self.launch_game(v, java_exe)
        else:
            self.btn_main.setEnabled(False)
            self.pb.show()
            self.pb.setValue(0)

            self.java_worker = JavaDownloaderWorker(req_ver, self.base_path)
            self.java_worker.progress.connect(self.pb.setValue)
            self.java_worker.status.connect(self.st_label.setText)
            self.java_worker.finished_signal.connect(lambda path: self.on_java_ready(v, path))
            self.java_worker.start()

    def on_java_ready(self, v, java_path):
        self.pb.hide()
        self.btn_main.setEnabled(True)
        self.launch_game(v, java_path)

    def launch_game(self, v, java_executable):
        self.st_label.setText("ЗАПУСК ИГРЫ...")

        options = {
            "username": self.nick.text().strip() or "Player",
            "uuid": "",
            "token": "",
            "jvmArguments": [f"-Xmx{self.settings.get('ram', 4)}G"],
            "executablePath": java_executable,
            "gameDirectory": self.base_path
        }

        try:
            cmd = mll.command.get_minecraft_command(v, self.base_path, options)

            self.launch_worker = LaunchWorker(cmd)
            self.launch_worker.started_signal.connect(self.on_game_started)
            self.launch_worker.crash_signal.connect(self.on_game_crash)
            self.launch_worker.finished_signal.connect(self.on_game_finished)
            self.launch_worker.start()

        except Exception as e:
            self.st_label.setText(f"Ошибка запуска: {e}")

    def on_game_started(self):
        self.hide()

    def on_game_crash(self, log_text):
        dialog = CrashDialog(log_text, self)
        dialog.exec()

    def on_game_finished(self):
        self.show()
        self.st_label.setText("Игра завершена")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RmyatoLauncher()
    window.show()
    sys.exit(app.exec())
