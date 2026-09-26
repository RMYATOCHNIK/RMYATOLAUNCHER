import sys
import os
import subprocess
import json
import requests
import shutil
import re
import minecraft_launcher_lib as mll
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QSpinBox, QGraphicsDropShadowEffect, QCheckBox, QListWidget,
    QListWidgetItem, QMessageBox, QStackedWidget, QTextEdit,
    QFrame, QTabWidget, QDialog, QFormLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QPropertyAnimation
from PyQt6.QtGui import QColor, QIcon, QCursor

PURPLE = "#8A2BE2"
ACCENT_HOVER = "#9A3BF2"
BG_DARK = "#0A0A0A"
CARD_BG = "#111111"
TEXT_MUTED = "#888888"


def get_launch_version_id(game_path, mc_version, loader):
    loader = loader.lower()
    versions_dir = os.path.join(game_path, "versions")
    
    if loader == "vanilla":
        v_path = os.path.join(versions_dir, mc_version)
        return mc_version if os.path.exists(v_path) else None

    if os.path.exists(versions_dir):
        for folder in os.listdir(versions_dir):
            folder_lower = folder.lower()
            if mc_version in folder and loader in folder_lower:
                return folder

    return None


class CreateProfileDialog(QDialog):
    def __init__(self, available_versions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создание новой сборки")
        self.setFixedSize(380, 260)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_DARK}; border: 2px solid {PURPLE}; border-radius: 12px; }}
            QLabel {{ color: white; font-weight: bold; font-size: 13px; }}
            QLineEdit, QComboBox {{ 
                background: {CARD_BG}; color: white; border: 1px solid #333; 
                padding: 8px; border-radius: 8px; font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {PURPLE}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("СОЗДАНИЕ СБОРКИ", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {PURPLE}; font-size: 16px; font-weight: 900;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Например: Мой Forge 1.12.2")

        self.version_combo = QComboBox()
        self.version_combo.addItems(available_versions)

        self.loader_combo = QComboBox()
        self.loader_combo.addItems(["Vanilla", "Forge", "Fabric"])

        form.addRow("Название:", self.name_input)
        form.addRow("Версия MC:", self.version_combo)
        form.addRow("Загрузчик:", self.loader_combo)
        layout.addLayout(form)

        layout.addSpacing(10)

        btn_create = QPushButton("СОЗДАТЬ СБОРКУ")
        btn_create.setFixedHeight(40)
        btn_create.setStyleSheet(f"""
            QPushButton {{
                background: {PURPLE}; color: white; font-weight: bold; 
                border-radius: 10px; font-size: 14px;
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER}; }}
        """)
        btn_create.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_create.clicked.connect(self.accept)
        layout.addWidget(btn_create)

    def get_data(self):
        name = self.name_input.text().strip() or "Новая сборка"
        folder_name = re.sub(r'[^\w\-_]', '_', name)
        return {
            "name": name,
            "version": self.version_combo.currentText(),
            "loader": self.loader_combo.currentText(),
            "folder": folder_name
        }


class InstallWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, version, path, loader_type="vanilla"):
        super().__init__()
        self.version = version
        self.path = path
        self.loader_type = loader_type.lower()

    def run(self):
        def update_p(v):
            self.progress.emit(int(v))

        def update_s(t):
            self.status.emit(str(t))

        callback = {"setStatus": update_s, "setProgress": update_p, "setMax": lambda v: None}
        try:
            update_s(f"Скачивание Vanilla {self.version}...")
            mll.install.install_minecraft_version(self.version, self.path, callback=callback)

            if self.loader_type == "forge":
                update_s("Поиск и установка Forge...")
                try:
                    forge_version = mll.forge.find_forge_version(self.version)
                    if forge_version:
                        mll.forge.install_forge_version(forge_version, self.path, callback=callback)
                    else:
                        update_s("Forge для этой версии не найден!")
                except Exception as e:
                    update_s(f"Ошибка установки Forge: {e}")

            elif self.loader_type == "fabric":
                update_s("Установка Fabric...")
                try:
                    mll.fabric.install_fabric(self.version, self.path, callback=callback)
                except Exception as e:
                    update_s(f"Ошибка установки Fabric: {e}")

            self.finished.emit(True)
        except Exception as e:
            self.status.emit(f"Ошибка установки: {e}")
            self.finished.emit(False)


class ModSearchWorker(QThread):
    results_ready = pyqtSignal(list, bool)
    error_signal = pyqtSignal(str)

    def __init__(self, query, game_version, loader_type, limit, offset):
        super().__init__()
        self.query = query
        self.game_version = game_version
        self.loader_type = loader_type.lower()
        self.limit = limit
        self.offset = offset

    def run(self):
        try:
            facets_list = [["project_type:mod"]]
            if self.game_version:
                facets_list.append([f"versions:{self.game_version}"])
            if self.loader_type in ["fabric", "forge", "neoforge", "quilt"]:
                facets_list.append([f"categories:{self.loader_type}"])

            facets = json.dumps(facets_list)
            url = f"https://api.modrinth.com/v2/search?query={self.query}&facets={facets}&limit={self.limit}&offset={self.offset}"
            response = requests.get(url, timeout=10).json()
            hits = response.get("hits", [])
            has_more = len(hits) >= self.limit
            self.results_ready.emit(hits, has_more)
        except Exception as e:
            self.error_signal.emit(str(e))


class ModDownloadWorker(QThread):
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, project_id, game_version, loader_type, profile_path):
        super().__init__()
        self.project_id = project_id
        self.game_version = game_version
        self.loader_type = loader_type.lower()
        self.profile_path = profile_path

    def run(self):
        try:
            self.status_signal.emit("Поиск версии мода...")
            versions_url = f"https://api.modrinth.com/v2/project/{self.project_id}/version"
            
            params = {
                "game_versions": f'["{self.game_version}"]',
                "loaders": f'["{self.loader_type}"]'
            }
            v_data = requests.get(versions_url, params=params, timeout=10).json()

            if not v_data and self.loader_type != "vanilla":
                params = {"game_versions": f'["{self.game_version}"]'}
                v_data = requests.get(versions_url, params=params, timeout=10).json()

            if not v_data:
                self.finished_signal.emit(
                    False, 
                    f"Этот мод недоступен для Minecraft {self.game_version} ({self.loader_type})!"
                )
                return

            target_file = None
            for v in v_data:
                if v.get('files'):
                    target_file = v['files'][0]
                    break

            if not target_file:
                self.finished_signal.emit(False, "Подходящий .jar файл не найден.")
                return

            file_url = target_file['url']
            file_name = target_file['filename']

            mods_dir = os.path.join(self.profile_path, "mods")
            os.makedirs(mods_dir, exist_ok=True)
            file_path = os.path.join(mods_dir, file_name)

            self.status_signal.emit(f"Загрузка {file_name}...")
            r = requests.get(file_url, timeout=15)
            with open(file_path, "wb") as f:
                f.write(r.content)

            self.finished_signal.emit(True, f"Мод {file_name} успешно установлен!")
        except Exception as e:
            self.finished_signal.emit(False, f"Ошибка скачивания: {e}")


class GameLaunchWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, launch_version_id, global_base_path, profile_path, username, ram, window_size):
        super().__init__()
        self.launch_version_id = launch_version_id
        self.global_base_path = global_base_path
        self.profile_path = profile_path
        self.username = username
        self.ram = ram
        self.window_size = window_size

    def run(self):
        options = {
            "username": self.username if self.username else "Player",
            "jvmArguments": [f"-Xmx{self.ram}G", "-Xms2G"],
            "gameDirectory": self.profile_path
        }
        if self.window_size:
            options["width"] = str(self.window_size[0])
            options["height"] = str(self.window_size[1])

        try:
            self.log_signal.emit(f"[LAUNCHER] Формирование команды запуска для {self.launch_version_id}...")
            cmd = mll.command.get_minecraft_command(self.launch_version_id, self.global_base_path, options)
            self.log_signal.emit("[LAUNCHER] Запуск процесса игры...")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                creationflags=0x08000000 if os.name == 'nt' else 0
            )

            for line in iter(proc.stdout.readline, ''):
                if line:
                    self.log_signal.emit(line.strip())

            proc.stdout.close()
            proc.wait()
            self.log_signal.emit("[LAUNCHER] Процесс игры завершен.")
        except Exception as e:
            self.log_signal.emit(f"[LAUNCHER ERROR] {e}")
        self.finished_signal.emit()


class RmyatoLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.base_path = os.path.join(os.getenv('APPDATA'), '.rmlauncher')
        self.profiles_file = os.path.join(self.base_path, "profiles.json")
        os.makedirs(self.base_path, exist_ok=True)

        self.settings = {
            "ram": 4,
            "snapshots": False,
            "width": 925,
            "height": 530,
            "game_path": self.base_path
        }

        self.profiles_data = {"active": "", "list": {}}
        self.available_versions = []

        self.offset = 0
        self.limit = 5
        self.is_loading_mods = False
        self.has_more_mods = True

        self.setWindowTitle("RmyatoLauncher - Minecraft Modded Client")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1000, 600)
        
        if os.path.exists("rmyatolauncher.ico"):
            self.setWindowIcon(QIcon("rmyatolauncher.ico"))

        self.fetch_available_versions()
        self.load_profiles()
        self.init_ui()
        self.refresh_profile_box()
        self.fade_in()

    def fetch_available_versions(self):
        try:
            all_v = mll.utils.get_version_list()
            self.available_versions = [v['id'] for v in all_v if v['type'] == 'release']
        except Exception:
            self.available_versions = ["1.20.1", "1.12.2", "1.16.5"]

    def load_profiles(self):
        if os.path.exists(self.profiles_file):
            try:
                with open(self.profiles_file, "r", encoding="utf-8") as f:
                    self.profiles_data = json.load(f)
            except Exception:
                pass

        if not self.profiles_data.get("list"):
            default_p = {
                "name": "Стандартная 1.20.1 Fabric",
                "version": "1.20.1",
                "loader": "Fabric",
                "folder": "Default_1_20_1"
            }
            self.profiles_data = {
                "active": default_p["name"],
                "list": {default_p["name"]: default_p}
            }
            self.save_profiles()

    def save_profiles(self):
        with open(self.profiles_file, "w", encoding="utf-8") as f:
            json.dump(self.profiles_data, f, ensure_ascii=False, indent=4)

    def get_active_profile(self):
        active_name = self.profiles_data.get("active")
        return self.profiles_data["list"].get(active_name, list(self.profiles_data["list"].values())[0])

    def get_active_profile_path(self):
        p = self.get_active_profile()
        path = os.path.join(self.base_path, "profiles", p["folder"])
        os.makedirs(path, exist_ok=True)
        return path

    def init_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QVBoxLayout(self.central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.content = QWidget()
        self.content.setStyleSheet(f"background: {BG_DARK}; border: 2px solid {PURPLE}; border-radius: 20px;")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(PURPLE))
        shadow.setOffset(0, 0)
        self.content.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(15, 10, 15, 15)
        self.main_layout.addWidget(self.content)

        self.init_titlebar()

        body_layout = QHBoxLayout()
        body_layout.setSpacing(15)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(10)

        self.btn_nav_main = self.create_nav_btn("ИГРА")
        self.btn_nav_mods = self.create_nav_btn("МОДЫ")
        self.btn_nav_logs = self.create_nav_btn("ЛОГИ")
        self.btn_nav_sett = self.create_nav_btn("НАСТРОЙКИ")

        self.btn_nav_main.clicked.connect(lambda: self.switch_page(0))
        self.btn_nav_mods.clicked.connect(lambda: self.switch_page(1))
        self.btn_nav_logs.clicked.connect(lambda: self.switch_page(2))
        self.btn_nav_sett.clicked.connect(lambda: self.switch_page(3))

        sidebar.addWidget(self.btn_nav_main)
        sidebar.addWidget(self.btn_nav_mods)
        sidebar.addWidget(self.btn_nav_logs)
        sidebar.addWidget(self.btn_nav_sett)
        sidebar.addStretch()

        btn_folder = QPushButton("Папка сборки")
        btn_folder.setStyleSheet("color: #AAA; border: none; text-align: left; padding: 5px;")
        btn_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_folder.clicked.connect(lambda: os.startfile(self.get_active_profile_path()))
        sidebar.addWidget(btn_folder)

        body_layout.addLayout(sidebar, stretch=1)

        self.pages = QStackedWidget()
        
        self.page_main = self.create_main_page()
        self.page_mods = self.create_mods_page()
        self.page_logs = self.create_logs_page()
        self.page_settings = self.create_settings_page()

        self.pages.addWidget(self.page_main)
        self.pages.addWidget(self.page_mods)
        self.pages.addWidget(self.page_logs)
        self.pages.addWidget(self.page_settings)

        body_layout.addWidget(self.pages, stretch=4)
        self.layout.addLayout(body_layout)

        self.switch_page(0)

    def init_titlebar(self):
        title_bar = QHBoxLayout()
        
        logo = QLabel("RMYATO LAUNCHER")
        logo.setStyleSheet(f"color: {PURPLE}; font-size: 18px; font-weight: 900; letter-spacing: 2px; border: none;")
        title_bar.addWidget(logo)

        title_bar.addStretch()

        btn_min = QPushButton("—")
        btn_min.setFixedSize(30, 30)
        btn_min.setStyleSheet("color: white; border: none; font-size: 16px; background: transparent;")
        btn_min.clicked.connect(self.showMinimized)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("QPushButton { color: white; border: none; font-size: 16px; background: transparent; } QPushButton:hover { color: #FF4444; }")
        btn_close.clicked.connect(self.close)

        title_bar.addWidget(btn_min)
        title_bar.addWidget(btn_close)

        self.layout.addLayout(title_bar)

    def create_nav_btn(self, text):
        btn = QPushButton(text)
        btn.setFixedHeight(45)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {CARD_BG};
                color: white;
                font-weight: bold;
                border: 1px solid #222;
                border-radius: 10px;
                text-align: left;
                padding-left: 15px;
            }}
            QPushButton:hover {{
                background: {PURPLE};
                border: 1px solid {ACCENT_HOVER};
            }}
        """)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return btn

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        buttons = [self.btn_nav_main, self.btn_nav_mods, self.btn_nav_logs, self.btn_nav_sett]
        for idx, btn in enumerate(buttons):
            if idx == index:
                btn.setStyleSheet(f"background: {PURPLE}; color: white; font-weight: bold; border-radius: 10px; text-align: left; padding-left: 15px;")
            else:
                btn.setStyleSheet(f"background: {CARD_BG}; color: white; font-weight: bold; border: 1px solid #222; border-radius: 10px; text-align: left; padding-left: 15px;")

        if index == 1:
            self.refresh_installed_mods()

    def create_main_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addStretch()

        center_card = QFrame()
        center_card.setStyleSheet(f"background: {CARD_BG}; border: 1px solid #222; border-radius: 20px; padding: 25px;")
        card_layout = QVBoxLayout(center_card)

        card_title = QLabel("ВЫБОР СБОРКИ", alignment=Qt.AlignmentFlag.AlignCenter)
        card_title.setStyleSheet(f"color: {PURPLE}; font-size: 22px; font-weight: bold; border: none;")
        card_layout.addWidget(card_title)

        card_layout.addSpacing(15)

        card_layout.addWidget(QLabel("Активная сборка:"))
        prof_layout = QHBoxLayout()
        
        self.profile_combo = QComboBox()
        self.profile_combo.setStyleSheet(f"QComboBox {{ background: #0A0A0A; color: {PURPLE}; border: 1px solid {PURPLE}; padding: 10px; border-radius: 10px; font-weight: bold; }}")
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        
        btn_add_profile = QPushButton("Создать сборку")
        btn_add_profile.setStyleSheet(f"background: {PURPLE}; color: white; font-weight: bold; padding: 10px 15px; border-radius: 10px;")
        btn_add_profile.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add_profile.clicked.connect(self.open_create_profile_dialog)

        btn_del_profile = QPushButton("Удалить")
        btn_del_profile.setStyleSheet("background: #C62828; color: white; font-weight: bold; padding: 10px 15px; border-radius: 10px;")
        btn_del_profile.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_del_profile.clicked.connect(self.delete_current_profile)

        prof_layout.addWidget(self.profile_combo, stretch=3)
        prof_layout.addWidget(btn_add_profile)
        prof_layout.addWidget(btn_del_profile)
        card_layout.addLayout(prof_layout)

        self.profile_info_label = QLabel("Версия: - | Загрузчик: -", alignment=Qt.AlignmentFlag.AlignCenter)
        self.profile_info_label.setStyleSheet("color: #AAA; font-size: 13px; font-weight: bold; border: none; margin-top: 5px;")
        card_layout.addWidget(self.profile_info_label)

        card_layout.addSpacing(10)

        card_layout.addWidget(QLabel("Имя игрока (Никнейм):"))
        self.nick = QLineEdit("RmyatoUser")
        self.nick.setStyleSheet(f"background: #0A0A0A; color: white; border: 1px solid {PURPLE}; padding: 10px; border-radius: 10px; font-size: 14px;")
        card_layout.addWidget(self.nick)

        card_layout.addSpacing(15)

        self.st_label = QLabel("ГОТОВ К ИГРЕ", alignment=Qt.AlignmentFlag.AlignCenter)
        self.st_label.setStyleSheet("color: #888; font-size: 12px; font-weight: bold; border: none;")
        card_layout.addWidget(self.st_label)

        self.pb = QProgressBar()
        self.pb.setFixedHeight(8)
        self.pb.setStyleSheet(f"QProgressBar {{ background: #222; border-radius: 4px; border: none; }} QProgressBar::chunk {{ background: {PURPLE}; border-radius: 4px; }}")
        self.pb.hide()
        card_layout.addWidget(self.pb)

        card_layout.addSpacing(10)

        self.btn_main = QPushButton("ИГРАТЬ")
        self.btn_main.setFixedHeight(60)
        self.btn_main.setStyleSheet(f"""
            QPushButton {{ 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PURPLE}, stop:1 #6A1B9A); 
                color: white; font-size: 22px; font-weight: bold; border-radius: 15px; 
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER}; }}
        """)
        self.btn_main.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_main.clicked.connect(self.handle_launch_click)
        card_layout.addWidget(self.btn_main)

        layout.addWidget(center_card)
        layout.addStretch()
        return page

    def create_mods_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid #222; background: {CARD_BG}; border-radius: 10px; }}
            QTabBar::tab {{ background: #0A0A0A; color: white; padding: 10px 20px; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
            QTabBar::tab:selected {{ background: {PURPLE}; font-weight: bold; }}
        """)

        tab_online = QWidget()
        online_layout = QVBoxLayout(tab_online)

        search_box = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск мода на Modrinth...")
        self.search_input.setStyleSheet(f"background: #0A0A0A; color: white; border: 1px solid {PURPLE}; padding: 8px; border-radius: 8px;")
        self.search_input.returnPressed.connect(self.new_mod_search)

        btn_search = QPushButton("Найти")
        btn_search.setStyleSheet(f"background: {PURPLE}; font-weight: bold; padding: 8px 15px; border-radius: 8px;")
        btn_search.clicked.connect(self.new_mod_search)

        search_box.addWidget(self.search_input)
        search_box.addWidget(btn_search)
        online_layout.addLayout(search_box)

        self.mod_list_widget = QListWidget()
        self.mod_list_widget.setStyleSheet(f"""
            QListWidget {{ background: #0A0A0A; border: 1px solid #222; border-radius: 8px; color: white; padding: 5px; }}
            QListWidget::item {{ padding: 10px; border-bottom: 1px solid #1A1A1A; }}
            QListWidget::item:selected {{ background: {PURPLE}; color: white; border-radius: 5px; }}
        """)
        self.mod_list_widget.verticalScrollBar().valueChanged.connect(self.check_mod_scroll)
        online_layout.addWidget(self.mod_list_widget)

        btn_dl_mod = QPushButton("СКАЧАТЬ В ТЕКУЩУЮ СБОРКУ")
        btn_dl_mod.setStyleSheet(f"background: {PURPLE}; font-weight: bold; padding: 10px; border-radius: 8px;")
        btn_dl_mod.clicked.connect(self.download_selected_mod)
        online_layout.addWidget(btn_dl_mod)

        tab_local = QWidget()
        local_layout = QVBoxLayout(tab_local)

        self.local_mods_widget = QListWidget()
        self.local_mods_widget.setStyleSheet(f"""
            QListWidget {{ background: #0A0A0A; border: 1px solid #222; border-radius: 8px; color: white; padding: 5px; }}
            QListWidget::item {{ padding: 10px; border-bottom: 1px solid #1A1A1A; }}
        """)
        local_layout.addWidget(self.local_mods_widget)

        local_btns = QHBoxLayout()
        btn_del_mod = QPushButton("Удалить выбранный мод")
        btn_del_mod.setStyleSheet("background: #C62828; color: white; font-weight: bold; padding: 10px; border-radius: 8px;")
        btn_del_mod.clicked.connect(self.delete_selected_mod)

        btn_open_mods_dir = QPushButton("Открыть папку модов сборки")
        btn_open_mods_dir.setStyleSheet(f"background: {PURPLE}; color: white; font-weight: bold; padding: 10px; border-radius: 8px;")
        btn_open_mods_dir.clicked.connect(lambda: os.startfile(os.path.join(self.get_active_profile_path(), "mods")))

        local_btns.addWidget(btn_del_mod)
        local_btns.addWidget(btn_open_mods_dir)
        local_layout.addLayout(local_btns)

        tabs.addTab(tab_online, "Каталог Modrinth")
        tabs.addTab(tab_local, "Моды сборки (.jar)")

        layout.addWidget(tabs)
        return page

    def create_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl = QLabel("КОНСОЛЬ ИГРЫ И ЛОГИ СИСТЕМЫ:")
        lbl.setStyleSheet(f"color: {PURPLE}; font-weight: bold;")
        layout.addWidget(lbl)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background: #050505; color: #00FF66; font-family: Consolas, Monospace; font-size: 12px; border: 1px solid #222; border-radius: 10px; padding: 10px;")
        layout.addWidget(self.log_console)

        btn_clear = QPushButton("Очистить логи")
        btn_clear.setStyleSheet("background: #222; color: white; padding: 6px; border-radius: 5px;")
        btn_clear.clicked.connect(self.log_console.clear)
        layout.addWidget(btn_clear)

        return page

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("ОБЩИЕ НАСТРОЙКИ ЛАУНЧЕРА")
        title.setStyleSheet(f"color: {PURPLE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Выделение оперативной памяти (ГБ):"))
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(2, 64)
        self.ram_spin.setValue(self.settings["ram"])
        self.ram_spin.setStyleSheet(f"background: {CARD_BG}; color: white; border: 1px solid {PURPLE}; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.ram_spin)

        layout.addWidget(QLabel("Разрешение окна игры (Ширина x Высота):"))
        res_layout = QHBoxLayout()
        self.res_w = QSpinBox()
        self.res_w.setRange(800, 3840)
        self.res_w.setValue(self.settings["width"])
        self.res_w.setStyleSheet(f"background: {CARD_BG}; color: white; border: 1px solid {PURPLE}; padding: 6px;")

        self.res_h = QSpinBox()
        self.res_h.setRange(600, 2160)
        self.res_h.setValue(self.settings["height"])
        self.res_h.setStyleSheet(f"background: {CARD_BG}; color: white; border: 1px solid {PURPLE}; padding: 6px;")

        res_layout.addWidget(self.res_w)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.res_h)
        layout.addLayout(res_layout)

        btn_save = QPushButton("СОХРАНИТЬ НАСТРОЙКИ")
        btn_save.setStyleSheet(f"background: {PURPLE}; color: white; font-weight: bold; padding: 12px; border-radius: 10px; margin-top: 10px;")
        btn_save.clicked.connect(self.save_settings)
        layout.addWidget(btn_save)

        layout.addStretch()
        return page

    def refresh_profile_box(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for name in self.profiles_data["list"].keys():
            self.profile_combo.addItem(name)
        active = self.profiles_data.get("active")
        if active in self.profiles_data["list"]:
            self.profile_combo.setCurrentText(active)
        self.profile_combo.blockSignals(False)
        self.update_profile_info()

    def update_profile_info(self):
        p = self.get_active_profile()
        self.profile_info_label.setText(f"Версия Minecraft: {p['version']} | Загрузчик: {p['loader']}")
        self.check_status()

    def on_profile_changed(self):
        selected_name = self.profile_combo.currentText()
        if selected_name and selected_name in self.profiles_data["list"]:
            self.profiles_data["active"] = selected_name
            self.save_profiles()
            self.update_profile_info()
            self.refresh_installed_mods()

    def open_create_profile_dialog(self):
        dialog = CreateProfileDialog(self.available_versions, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data["name"] in self.profiles_data["list"]:
                QMessageBox.warning(self, "Ошибка", "Сборка с таким названием уже существует!")
                return
            
            self.profiles_data["list"][data["name"]] = data
            self.profiles_data["active"] = data["name"]
            self.save_profiles()
            self.refresh_profile_box()

    def delete_current_profile(self):
        if len(self.profiles_data["list"]) <= 1:
            QMessageBox.warning(self, "Ошибка", "Нельзя удалить единственную сборку!")
            return

        active_name = self.profiles_data.get("active")
        reply = QMessageBox.question(
            self, "Удаление сборки", 
            f"Вы уверены, что хотите удалить сборку '{active_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.profiles_data["list"][active_name]
            first_remaining = list(self.profiles_data["list"].keys())[0]
            self.profiles_data["active"] = first_remaining
            self.save_profiles()
            self.refresh_profile_box()

    def log_message(self, text):
        self.log_console.append(text)

    def save_settings(self):
        self.settings["ram"] = self.ram_spin.value()
        self.settings["width"] = self.res_w.value()
        self.settings["height"] = self.res_h.value()
        QMessageBox.information(self, "Сохранено", "Настройки успешно сохранены!")

    def check_status(self):
        p = self.get_active_profile()
        launch_id = get_launch_version_id(self.settings["game_path"], p["version"], p["loader"])
        if launch_id:
            self.btn_main.setText("ИГРАТЬ")
            self.st_label.setText("СБОРКА ГОТОВА")
        else:
            self.btn_main.setText("СКАЧАТЬ И ИГРАТЬ")
            self.st_label.setText("НУЖНО ЗАГРУЗИТЬ ФАЙЛЫ")

    def handle_launch_click(self):
        p = self.get_active_profile()
        launch_id = get_launch_version_id(self.settings["game_path"], p["version"], p["loader"])

        if not launch_id:
            self.pb.show()
            self.btn_main.setEnabled(False)
            self.install_worker = InstallWorker(p["version"], self.settings["game_path"], p["loader"])
            self.install_worker.progress.connect(self.pb.setValue)
            self.install_worker.status.connect(self.st_label.setText)
            self.install_worker.finished.connect(self.on_install_finished)
            self.install_worker.start()
        else:
            self.launch_game(launch_id)

    def on_install_finished(self, success):
        self.pb.hide()
        self.btn_main.setEnabled(True)
        self.check_status()
        if success:
            p = self.get_active_profile()
            launch_id = get_launch_version_id(self.settings["game_path"], p["version"], p["loader"])
            if launch_id:
                self.launch_game(launch_id)

    def launch_game(self, launch_id):
        p = self.get_active_profile()
        username = self.nick.text().strip()
        profile_path = self.get_active_profile_path()

        self.log_message(f"[LAUNCHER] Запуск сборки '{p['name']}' ({launch_id})...")
        self.btn_main.setEnabled(False)
        self.st_label.setText("ИГРА ЗАПУСКАЕТСЯ...")

        self.launch_worker = GameLaunchWorker(
            launch_id, self.settings["game_path"], profile_path, username,
            self.settings["ram"], (self.settings["width"], self.settings["height"])
        )
        self.launch_worker.log_signal.connect(self.log_message)
        self.launch_worker.finished_signal.connect(self.on_game_finished)
        self.launch_worker.start()

    def on_game_finished(self):
        self.btn_main.setEnabled(True)
        self.check_status()

    def new_mod_search(self):
        self.offset = 0
        self.has_more_mods = True
        self.mod_list_widget.clear()
        self.load_mods_online()

    def load_mods_online(self):
        if self.is_loading_mods or not self.has_more_mods:
            return

        self.is_loading_mods = True
        query = self.search_input.text()
        p = self.get_active_profile()

        self.mod_search_worker = ModSearchWorker(query, p["version"], p["loader"], self.limit, self.offset)
        self.mod_search_worker.results_ready.connect(self.on_mods_loaded)
        self.mod_search_worker.error_signal.connect(lambda e: self.log_message(f"[MOD ERROR] {e}"))
        self.mod_search_worker.start()

    def on_mods_loaded(self, hits, has_more):
        self.has_more_mods = has_more
        if not hits and self.offset == 0:
            self.mod_list_widget.addItem("Ничего не найдено.")
        else:
            for mod in hits:
                item = QListWidgetItem(f"{mod['title']}\n{mod['description']}")
                item.setData(Qt.ItemDataRole.UserRole, mod['project_id'])
                self.mod_list_widget.addItem(item)

        self.offset += self.limit
        self.is_loading_mods = False

    def check_mod_scroll(self, value):
        scrollbar = self.mod_list_widget.verticalScrollBar()
        if value >= scrollbar.maximum() - 5:
            self.load_mods_online()

    def download_selected_mod(self):
        selected = self.mod_list_widget.currentItem()
        if not selected:
            return
        project_id = selected.data(Qt.ItemDataRole.UserRole)
        if not project_id:
            return

        p = self.get_active_profile()
        profile_path = self.get_active_profile_path()

        self.st_label.setText("СКАЧИВАНИЕ МОДА...")

        self.mod_dl_worker = ModDownloadWorker(project_id, p["version"], p["loader"], profile_path)
        self.mod_dl_worker.status_signal.connect(self.log_message)
        self.mod_dl_worker.finished_signal.connect(self.on_mod_download_finished)
        self.mod_dl_worker.start()

    def on_mod_download_finished(self, success, message):
        self.st_label.setText("ГОТОВ К ИГРЕ")
        if success:
            QMessageBox.information(self, "Мод загружен", message)
            self.refresh_installed_mods()
        else:
            QMessageBox.warning(self, "Ошибка мода", message)

    def refresh_installed_mods(self):
        self.local_mods_widget.clear()
        mods_dir = os.path.join(self.get_active_profile_path(), "mods")
        if not os.path.exists(mods_dir):
            return

        files = [f for f in os.listdir(mods_dir) if f.endswith(".jar")]
        if not files:
            self.local_mods_widget.addItem("В этой сборке еще нет модов.")
            return

        for file in files:
            item = QListWidgetItem(f"{file}")
            item.setData(Qt.ItemDataRole.UserRole, file)
            self.local_mods_widget.addItem(item)

    def delete_selected_mod(self):
        selected = self.local_mods_widget.currentItem()
        if not selected:
            return
        filename = selected.data(Qt.ItemDataRole.UserRole)
        if not filename:
            return

        file_path = os.path.join(self.get_active_profile_path(), "mods", filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                QMessageBox.information(self, "Удалено", f"Мод {filename} удален.")
                self.refresh_installed_mods()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")

    def fade_in(self):
        self.setWindowOpacity(0.0)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if hasattr(self, "old_pos"):
            delta = QPoint(e.globalPosition().toPoint() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = e.globalPosition().toPoint()


if __name__ == "__main__":
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("rmyato.launcher.2.0")

    app = QApplication(sys.argv)
    window = RmyatoLauncher()
    window.show()
    sys.exit(app.exec())
