import os
import sys
import mmap
import time
import csv
from datetime import datetime
from PyQt6.QtGui import QAction, QColor, QPalette, QBrush, QIcon, QPixmap, QPainter, QFont, QPolygonF, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QGroupBox,
    QFileDialog, QMessageBox, QProgressBar, QHeaderView, QDialog, QTextBrowser,
    QComboBox, QCheckBox, QFrame, QSizePolicy, QStyleFactory
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF, QSize, QDir

# ====================== НАСТРОЙКИ ТЕМ ======================
DARK_THEME = {
    "background": "#121212",
    "foreground": "#E0E0E0",
    "accent": "#1E1E1E",
    "highlight": "#3A6DFF",
    "button": "#2D3D6B",
    "button_hover": "#4A5A98",
    "text": "#F0F0F0",
    "success": "#4CAF50",
    "error": "#FF5252",
    "table_header": "#1A1A2E",
    "table_row_even": "#252538",
    "table_row_odd": "#2D2D44",
    "dialog": "#1E1E2E",
    "input": "#2A2A4A",
    "input_text": "#FFFFFF",
    "link": "#6C8BFF",
    "warning": "#FFA500",
    "border": "#3A4A8A",
    "card": "#1A1A2E"
}

CURRENT_THEME = DARK_THEME

class FileSearchWorker(QThread):
    update_progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    found_match = pyqtSignal(str, str, str, str)  # file_path, filename, size, modified

    def __init__(self, search_path, extensions, keywords, max_size_mb, skip_binary, match_type):
        super().__init__()
        self.search_path = search_path
        self.extensions = self.normalize_extensions(extensions)
        self.keywords = [kw.strip().lower() for kw in keywords.split(',') if kw.strip()]
        self.results = []
        self.is_running = True
        self.file_count = 0
        self.processed_files = 0
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.skip_binary = skip_binary
        self.match_type = match_type

    def normalize_extensions(self, extensions):
        normalized = []
        for ext in extensions.split(','):
            ext = ext.strip().lower()
            if not ext:
                continue
            if not ext.startswith('.'):
                ext = '.' + ext
            normalized.append(ext)
        return normalized

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            # Считаем общее количество файлов
            self.file_count = self.count_files(self.search_path)
            if self.file_count == 0:
                self.error.emit("Файлы с указанными расширениями не найдены")
                return

            # Рекурсивный поиск
            self.search_files(self.search_path)
            self.finished.emit(self.results)
        except Exception as e:
            self.error.emit(f"Ошибка поиска: {str(e)}")

    def count_files(self, path):
        count = 0
        for root, _, files in os.walk(path):
            for file in files:
                if not self.is_running:
                    return 0
                    
                file_path = os.path.join(root, file)
                # Пропускаем скрытые файлы/папки
                if any(part.startswith('.') for part in file_path.split(os.sep)):
                    continue
                    
                ext = os.path.splitext(file)[1].lower()
                if ext in self.extensions:
                    try:
                        # Пропускаем большие файлы
                        if os.path.getsize(file_path) > self.max_size_bytes:
                            continue
                        count += 1
                    except:
                        continue
        return count

    def search_files(self, path):
        for root, _, files in os.walk(path):
            if not self.is_running:
                return
                
            for file in files:
                if not self.is_running:
                    return
                    
                file_path = os.path.join(root, file)
                
                # Пропускаем скрытые файлы/папки
                if any(part.startswith('.') for part in file_path.split(os.sep)):
                    continue
                    
                ext = os.path.splitext(file)[1].lower()
                
                if ext in self.extensions:
                    try:
                        file_size = os.path.getsize(file_path)
                        # Пропускаем большие файлы
                        if file_size > self.max_size_bytes:
                            continue
                            
                        self.processed_files += 1
                        progress = int((self.processed_files / self.file_count) * 100)
                        self.update_progress.emit(
                            progress, 
                            self.file_count, 
                            f"Обработка: {file}"
                        )
                        
                        # Получаем дату изменения
                        modified = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%d.%m.%Y %H:%M")
                        
                        # Оптимизированный поиск с использованием mmap
                        with open(file_path, 'rb') as f:
                            # Пропускаем бинарные файлы
                            if self.skip_binary:
                                try:
                                    content = f.read(1024)
                                    if b'\x00' in content:
                                        continue
                                    # Возвращаем указатель в начало файла
                                    f.seek(0)
                                except:
                                    continue
                                
                            try:
                                # Используем mmap для быстрого поиска
                                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                                    text = mm.read().decode('utf-8', errors='ignore').lower()
                                    
                                    # Поиск по ключевым словам
                                    found = False
                                    if not self.keywords:  # Если ключевых слов нет
                                        found = True
                                    elif self.match_type == "any":
                                        for keyword in self.keywords:
                                            if keyword in text:
                                                found = True
                                                break
                                    else:  # all
                                        found = all(keyword in text for keyword in self.keywords)
                                    
                                    if found:
                                        # Форматируем размер файла
                                        size_str = self.format_size(file_size)
                                        self.found_match.emit(file_path, file, size_str, modified)
                                        self.results.append({
                                            "file_path": file_path,
                                            "filename": file,
                                            "size": size_str,
                                            "modified": modified
                                        })
                            except Exception as e:
                                # Ошибка mmap - пробуем обычный способ
                                try:
                                    content = f.read(min(1024*1024, file_size)).decode('utf-8', errors='ignore').lower()
                                    
                                    found = False
                                    if not self.keywords:
                                        found = True
                                    elif self.match_type == "any":
                                        for keyword in self.keywords:
                                            if keyword in content:
                                                found = True
                                                break
                                    else:  # all
                                        found = all(keyword in content for keyword in self.keywords)
                                    
                                    if found:
                                        size_str = self.format_size(file_size)
                                        self.found_match.emit(file_path, file, size_str, modified)
                                        self.results.append({
                                            "file_path": file_path,
                                            "filename": file,
                                            "size": size_str,
                                            "modified": modified
                                        })
                                except:
                                    continue
                    except Exception as e:
                        continue

    def format_size(self, size):
        # Конвертируем размер в читаемый формат
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ТБ"

class ModernCard(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CURRENT_THEME['card']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(self.layout)
        
        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet(f"""
                QLabel {{
                    color: {CURRENT_THEME['highlight']};
                    font-weight: bold;
                    font-size: 12pt;
                    padding-bottom: 5px;
                }}
            """)
            self.layout.addWidget(title_label)

class XillenFileFinder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xillen File Finder")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)
        
        # Создаем и устанавливаем иконку
        self.setWindowIcon(QIcon(self.create_icon()))
        
        # Основной виджет
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_widget.setLayout(main_layout)
        
        # Создание меню
        self.create_menu()
        
        # Заголовок
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 10)
        
        # Логотип и название
        logo_layout = QHBoxLayout()
        
        logo_label = QLabel()
        logo_pixmap = QPixmap(self.create_icon()).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        
        title_layout = QVBoxLayout()
        title_label = QLabel("Xillen File Finder")
        title_label.setStyleSheet(f"""
            color: {CURRENT_THEME['highlight']};
            font-size: 24pt;
            font-weight: bold;
            font-family: 'Segoe UI', Arial, sans-serif;
        """)
        
        subtitle_label = QLabel("Быстрый и эффективный поиск файлов")
        subtitle_label.setStyleSheet(f"""
            color: {CURRENT_THEME['text']};
            font-size: 10pt;
            font-family: 'Segoe UI', Arial, sans-serif;
        """)
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        
        logo_layout.addWidget(logo_label)
        logo_layout.addLayout(title_layout)
        logo_layout.addStretch()
        
        # Авторы
        self.authors_label = QLabel()
        self.update_authors_label()
        self.authors_label.setOpenExternalLinks(True)
        self.authors_label.setStyleSheet(f"font-size: 10pt;")
        
        header_layout.addLayout(logo_layout, 1)
        header_layout.addWidget(self.authors_label, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        
        main_layout.addLayout(header_layout)
        
        # Основной контент
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Левая панель - настройки
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout()
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_panel.setLayout(left_layout)
        
        # Карточка настроек
        settings_card = ModernCard("Настройки поиска")
        settings_layout = QVBoxLayout()
        settings_card.layout.addLayout(settings_layout)
        
        # Выбор папки
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Папка поиска:"))
        
        self.path_label = QLabel("Выберите папку")
        self.path_label.setStyleSheet(f"""
            QLabel {{
                color: {CURRENT_THEME['text']}; 
                font-size: 11pt;
                background-color: {CURRENT_THEME['input']};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        self.path_label.setMinimumHeight(30)
        path_layout.addWidget(self.path_label, 1)
        
        self.browse_btn = QPushButton("Обзор...")
        self.browse_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CURRENT_THEME['button']};
                color: white;
                border: none;
                padding: 5px 10px;
                font-size: 10pt;
                border-radius: 4px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {CURRENT_THEME['button_hover']};
            }}
        """)
        self.browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(self.browse_btn)
        
        settings_layout.addLayout(path_layout)
        
        # Расширения файлов
        settings_layout.addWidget(QLabel("Расширения файлов:"))
        self.ext_input = QLineEdit(".txt, .pdf, .docx, .xlsx, .pptx")
        self.ext_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {CURRENT_THEME['input']}; 
                color: {CURRENT_THEME['input_text']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        self.ext_input.setPlaceholderText("Введите расширения через запятую")
        settings_layout.addWidget(self.ext_input)
        
        # Ключевые слова
        settings_layout.addWidget(QLabel("Ключевые слова:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Введите слова через запятую")
        self.keyword_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {CURRENT_THEME['input']}; 
                color: {CURRENT_THEME['input_text']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        settings_layout.addWidget(self.keyword_input)
        
        # Тип поиска
        settings_layout.addWidget(QLabel("Тип поиска:"))
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItem("Найти любое из слов (OR)")
        self.match_type_combo.addItem("Найти все слова (AND)")
        self.match_type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {CURRENT_THEME['input']}; 
                color: {CURRENT_THEME['input_text']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        settings_layout.addWidget(self.match_type_combo)
        
        # Дополнительные настройки
        options_layout = QGridLayout()
        options_layout.setHorizontalSpacing(15)
        
        # Максимальный размер файла
        options_layout.addWidget(QLabel("Макс. размер файла:"), 0, 0)
        
        self.max_size_input = QComboBox()
        self.max_size_input.addItems(["1", "5", "10", "20", "50", "100", "500", "1000"])
        self.max_size_input.setCurrentText("50")
        self.max_size_input.setStyleSheet(f"""
            QComboBox {{
                background-color: {CURRENT_THEME['input']}; 
                color: {CURRENT_THEME['input_text']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        options_layout.addWidget(self.max_size_input, 0, 1)
        
        # Пропускать бинарные файлы
        self.skip_binary_check = QCheckBox("Пропускать бинарные файлы")
        self.skip_binary_check.setChecked(True)
        options_layout.addWidget(self.skip_binary_check, 1, 0, 1, 2)
        
        settings_layout.addLayout(options_layout)
        
        left_layout.addWidget(settings_card)
        
        # Карточка управления
        control_card = ModernCard("Управление поиском")
        control_layout = QVBoxLayout()
        control_card.layout.addLayout(control_layout)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.search_btn = QPushButton("Начать поиск")
        self.search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CURRENT_THEME['highlight']};
                color: white;
                border: none;
                padding: 12px 20px;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #2A5BFF;
            }}
            QPushButton:disabled {{
                background-color: #5A6BAA;
            }}
        """)
        self.search_btn.setIcon(QIcon.fromTheme("system-search"))
        self.search_btn.clicked.connect(self.start_search)
        
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CURRENT_THEME['error']};
                color: white;
                border: none;
                padding: 12px 20px;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #FF4444;
            }}
            QPushButton:disabled {{
                background-color: #AA5A5A;
            }}
        """)
        self.stop_btn.setIcon(QIcon.fromTheme("process-stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_search)
        
        buttons_layout.addWidget(self.search_btn)
        buttons_layout.addWidget(self.stop_btn)
        
        control_layout.addLayout(buttons_layout)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 5px;
                text-align: center;
                background: {CURRENT_THEME['dialog']};
                height: 20px;
                font-size: 10pt;
                color: {CURRENT_THEME['text']};
            }}
            QProgressBar::chunk {{
                background: {CURRENT_THEME['highlight']};
                border-radius: 4px;
            }}
        """)
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)
        
        # Статистика
        self.stats_label = QLabel("Ожидание запуска...")
        self.stats_label.setStyleSheet(f"color: {CURRENT_THEME['text']}; font-size: 10pt;")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.stats_label)
        
        left_layout.addWidget(control_card)
        left_layout.addStretch()
        
        # Правая панель - результаты
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_panel.setLayout(right_layout)
        
        # Карточка результатов
        results_card = ModernCard("Результаты поиска")
        results_layout = QVBoxLayout()
        results_card.layout.addLayout(results_layout)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Имя файла", "Размер", "Изменен", "Путь"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.doubleClicked.connect(self.open_file)
        
        results_layout.addWidget(self.results_table)
        
        # Кнопки экспорта
        export_layout = QHBoxLayout()
        export_layout.setSpacing(10)
        
        self.export_csv_btn = QPushButton("Экспорт в CSV")
        self.export_csv_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CURRENT_THEME['success']};
                color: white;
                border: none;
                padding: 8px 15px;
                font-size: 11pt;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #3e8e41;
            }}
            QPushButton:disabled {{
                background-color: #5A7A5A;
            }}
        """)
        self.export_csv_btn.setIcon(QIcon.fromTheme("document-export"))
        self.export_csv_btn.clicked.connect(self.export_csv)
        self.export_csv_btn.setEnabled(False)
        
        self.open_file_btn = QPushButton("Открыть файл")
        self.open_file_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CURRENT_THEME['highlight']};
                color: white;
                border: none;
                padding: 8px 15px;
                font-size: 11pt;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #2A5BFF;
            }}
            QPushButton:disabled {{
                background-color: #5A6BAA;
            }}
        """)
        self.open_file_btn.setIcon(QIcon.fromTheme("document-open"))
        self.open_file_btn.clicked.connect(self.open_selected_file)
        self.open_file_btn.setEnabled(False)
        
        export_layout.addWidget(self.export_csv_btn)
        export_layout.addWidget(self.open_file_btn)
        export_layout.addStretch()
        
        results_layout.addLayout(export_layout)
        
        right_layout.addWidget(results_card)
        
        content_layout.addWidget(left_panel)
        content_layout.addWidget(right_panel, 1)
        
        main_layout.addLayout(content_layout, 1)
        
        # Статус
        self.status_label = QLabel("Готов к запуску поиска")
        self.status_label.setStyleSheet(f"""
            background-color: {CURRENT_THEME['card']};
            color: {CURRENT_THEME['button']}; 
            font-size: 10pt; 
            padding: 8px;
            border-radius: 4px;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Переменные для поиска
        self.search_thread = None
        self.start_time = None
        self.current_path = ""
        
        # Применение темы
        self.apply_theme()

    def update_authors_label(self):
        color = CURRENT_THEME['link']
        self.authors_label.setText(f"""
            <div style="text-align: right;">
                <p style="margin: 2px;">Разработчики:</p>
                <p style="margin: 2px;">
                    <a href="https://t.me/BengaminButton" style="color: {color}; text-decoration: none;">@Bengamin_Button</a> | 
                    <a href="https://t.me/xillenadapter" style="color: {color}; text-decoration: none;">@XillenAdapter</a>
                </p>
            </div>
        """)

    def create_menu(self):
        menu_bar = self.menuBar()
        
        # Меню Файл
        file_menu = menu_bar.addMenu("Файл")
        
        exit_action = QAction("Выход", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Меню Помощь
        help_menu = menu_bar.addMenu("Помощь")
        
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def apply_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(CURRENT_THEME['background']))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(CURRENT_THEME['text']))
        palette.setColor(QPalette.ColorRole.Base, QColor(CURRENT_THEME['dialog']))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(CURRENT_THEME['accent']))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(CURRENT_THEME['dialog']))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(CURRENT_THEME['text']))
        palette.setColor(QPalette.ColorRole.Text, QColor(CURRENT_THEME['text']))
        palette.setColor(QPalette.ColorRole.Button, QColor(CURRENT_THEME['button']))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("white"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(CURRENT_THEME['highlight']))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
        self.setPalette(palette)
        
        # Обновляем стили для всех виджетов
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {CURRENT_THEME['background']};
                color: {CURRENT_THEME['text']};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
            }}
            QLabel {{
                color: {CURRENT_THEME['text']};
            }}
            QLineEdit, QComboBox, QCheckBox {{
                background-color: {CURRENT_THEME['input']};
                color: {CURRENT_THEME['input_text']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 4px;
                padding: 5px;
            }}
            QTableWidget {{
                background-color: {CURRENT_THEME['dialog']};
                color: {CURRENT_THEME['text']};
                gridline-color: {CURRENT_THEME['border']};
                font-size: 10pt;
                border-radius: 4px;
                border: 1px solid {CURRENT_THEME['border']};
                alternate-background-color: {CURRENT_THEME['table_row_odd']};
            }}
            QHeaderView::section {{
                background-color: {CURRENT_THEME['table_header']};
                color: {CURRENT_THEME['text']};
                padding: 8px;
                border: none;
                font-weight: bold;
            }}
            QLabel a {{
                color: {CURRENT_THEME['link']};
                text-decoration: none;
            }}
            QLabel a:hover {{
                text-decoration: underline;
            }}
            QMenuBar {{
                background-color: {CURRENT_THEME['card']};
                color: {CURRENT_THEME['text']};
                padding: 5px;
                border-bottom: 1px solid {CURRENT_THEME['border']};
            }}
            QMenuBar::item {{
                padding: 5px 10px;
                background: transparent;
            }}
            QMenuBar::item:selected {{
                background: {CURRENT_THEME['button']};
                border-radius: 4px;
            }}
            QMenu {{
                background-color: {CURRENT_THEME['card']};
                border: 1px solid {CURRENT_THEME['border']};
                border-radius: 4px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 5px 25px 5px 20px;
            }}
            QMenu::item:selected {{
                background-color: {CURRENT_THEME['button']};
                border-radius: 4px;
            }}
        """)
        
        self.results_table.setAlternatingRowColors(True)

    def create_icon(self):
        # Уменьшенный размер иконки для решения проблемы Wayland
        size = 128
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Фон - круг
        painter.setBrush(QBrush(QColor(CURRENT_THEME['highlight'])))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        
        # Буква X - используем целочисленные координаты
        painter.setPen(QPen(QColor("white"), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        offset = int(size * 0.25)  # Преобразуем в целое число
        painter.drawLine(offset, offset, size - offset, size - offset)
        painter.drawLine(size - offset, offset, offset, size - offset)
        
        painter.end()
        return pixmap

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для поиска")
        if folder:
            self.current_path = folder
            self.path_label.setText(self.current_path)
            self.path_label.setToolTip(self.current_path)

    def start_search(self):
        if not self.current_path:
            self.browse_folder()
            if not self.current_path:
                return
                
        search_path = self.current_path
        extensions = self.ext_input.text().strip()
        keywords = self.keyword_input.text().strip()
        max_size_mb = int(self.max_size_input.currentText().strip())
        skip_binary = self.skip_binary_check.isChecked()
        match_type = "any" if self.match_type_combo.currentIndex() == 0 else "all"
        
        if not search_path:
            self.show_error("Пожалуйста, выберите папку для поиска")
            return
            
        if not os.path.exists(search_path):
            self.show_error("Указанный путь не существует")
            return
            
        if not extensions:
            self.show_error("Пожалуйста, укажите расширения файлов")
            return
            
        # Сброс таблицы
        self.results_table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.export_csv_btn.setEnabled(False)
        self.open_file_btn.setEnabled(False)
        self.status_label.setText("Подготовка к поиску...")
        self.status_label.setStyleSheet(f"background-color: {CURRENT_THEME['card']}; color: {CURRENT_THEME['button']};")
        self.start_time = time.time()
        
        # Запуск потока поиска
        self.search_thread = FileSearchWorker(
            search_path,
            extensions,
            keywords,
            max_size_mb,
            skip_binary,
            match_type
        )
        self.search_thread.update_progress.connect(self.update_progress)
        self.search_thread.finished.connect(self.search_finished)
        self.search_thread.error.connect(self.show_error)
        self.search_thread.found_match.connect(self.add_result_row)
        self.search_thread.start()

    def stop_search(self):
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.stop()
            self.search_thread.wait()
            self.search_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("Поиск остановлен пользователем")
            self.status_label.setStyleSheet(f"background-color: {CURRENT_THEME['card']}; color: {CURRENT_THEME['error']};")

    def update_progress(self, progress, total_files, message):
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"{message} ({progress}%)")
        
        elapsed = time.time() - self.start_time
        files_per_sec = self.search_thread.processed_files / elapsed if elapsed > 0 else 0
        remaining = (100 - progress) * elapsed / progress if progress > 0 else 0
        
        self.stats_label.setText(
            f"Обработано: {self.search_thread.processed_files}/{total_files} файлов | "
            f"Скорость: {files_per_sec:.1f} файл/сек | "
            f"Осталось: {remaining:.1f} сек | "
            f"Найдено: {self.results_table.rowCount()}"
        )

    def add_result_row(self, file_path, filename, size, modified):
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        
        # Имя файла
        file_item = QTableWidgetItem(filename)
        file_item.setData(Qt.ItemDataRole.UserRole, file_path)
        file_item.setToolTip(file_path)
        self.results_table.setItem(row, 0, file_item)
        
        # Размер
        size_item = QTableWidgetItem(size)
        self.results_table.setItem(row, 1, size_item)
        
        # Дата изменения
        modified_item = QTableWidgetItem(modified)
        self.results_table.setItem(row, 2, modified_item)
        
        # Путь
        path = os.path.dirname(file_path)
        path_item = QTableWidgetItem(path)
        path_item.setToolTip(path)
        self.results_table.setItem(row, 3, path_item)
        
        # Активируем кнопки
        self.export_csv_btn.setEnabled(True)
        self.open_file_btn.setEnabled(True)

    def search_finished(self, results):
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_csv_btn.setEnabled(len(results) > 0)
        self.open_file_btn.setEnabled(len(results) > 0)
        
        elapsed = time.time() - self.start_time
        files_per_sec = self.search_thread.processed_files / elapsed if elapsed > 0 else 0
        
        self.status_label.setText(
            f"Поиск завершен! Найдено файлов: {len(results)} | "
            f"Время: {elapsed:.1f} сек | "
            f"Скорость: {files_per_sec:.1f} файл/сек"
        )
        self.status_label.setStyleSheet(f"background-color: {CURRENT_THEME['card']}; color: {CURRENT_THEME['success']};")
        
        if not results:
            QMessageBox.information(self, "Поиск завершен", "Файлы с указанным текстом не найдены")

    def open_file(self, index):
        if index.isValid():
            file_path = self.results_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            self.open_file_path(file_path)

    def open_selected_file(self):
        selected = self.results_table.selectedItems()
        if selected:
            row = selected[0].row()
            file_path = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.open_file_path(file_path)

    def open_file_path(self, file_path):
        try:
            if not os.path.exists(file_path):
                self.show_error("Файл не найден!")
                return
                
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.call(["open", file_path])
            else:
                import subprocess
                subprocess.call(["xdg-open", file_path])
        except Exception as e:
            self.show_error(f"Не удалось открыть файл: {str(e)}")

    def show_error(self, message):
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.stop()
            self.search_thread.wait()
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"Ошибка: {message}")
        self.status_label.setStyleSheet(f"background-color: {CURRENT_THEME['card']}; color: {CURRENT_THEME['error']};")
        QMessageBox.critical(self, "Ошибка", message)

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить CSV", "xillen_results.csv", "CSV Files (*.csv)")
        if not filename:
            return
            
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(["Файл", "Размер", "Изменен", "Путь"])
                
                for row in range(self.results_table.rowCount()):
                    filename = self.results_table.item(row, 0).text()
                    size = self.results_table.item(row, 1).text()
                    modified = self.results_table.item(row, 2).text()
                    path = self.results_table.item(row, 3).text()
                    writer.writerow([filename, size, modified, path])
                    
            QMessageBox.information(self, "Успех", f"Данные экспортированы в {filename}")
        except Exception as e:
            self.show_error(f"Ошибка экспорта: {str(e)}")

    def show_about(self):
        about_text = f"""
        <html>
        <head>
        <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12pt;
            color: {CURRENT_THEME['text']};
            background-color: {CURRENT_THEME['background']};
        }}
        h1 {{
            color: {CURRENT_THEME['highlight']};
            text-align: center;
        }}
        .logo {{
            display: block;
            margin: 0 auto;
            width: 80px;
            height: 80px;
        }}
        .authors {{
            font-weight: bold;
            margin-top: 15px;
        }}
        .features {{
            margin-top: 15px;
        }}
        a {{
            color: {CURRENT_THEME['link']};
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        </style>
        </head>
        <body>
        <h1>Xillen File Finder</h1>
        <div style="text-align:center; margin-bottom:15px;">
            <img src="icon.png" class="logo" />
        </div>
        
        <div class="authors">Авторы:</div>
        <ul>
            <li><a href="https://t.me/BengaminButton">@Bengamin_Button</a></li>
            <li><a href="https://t.me/xillenadapter">@XillenAdapter</a></li>
        </ul>
        
        <div class="features">
            <p>Основные возможности:</p>
            <ul>
                <li>Быстрый поиск по содержимому файлов</li>
                <li>Поддержка форматов: TXT, PDF, DOCX, XLSX и других</li>
                <li>Гибкая фильтрация по ключевым словам</li>
                <li>Оптимизированный алгоритм с использованием mmap</li>
                <li>Пропуск бинарных файлов</li>
                <li>Экспорт результатов в CSV</li>
                <li>Темная тема оформления</li>
            </ul>
        </div>
        
        <p style="margin-top:20px; text-align:center;">Версия 4.0 | © 2023 Xillen Killers Project</p>
        </body>
        </html>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("О программе")
        msg.setIconPixmap(QPixmap(self.create_icon()).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio))
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(about_text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Применяем темную тему к диалогу
        msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: {CURRENT_THEME['background']};
                color: {CURRENT_THEME['text']};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QLabel {{
                color: {CURRENT_THEME['text']};
            }}
            QPushButton {{
                background-color: {CURRENT_THEME['button']};
                color: white;
                padding: 5px 15px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {CURRENT_THEME['button_hover']};
            }}
        """)
        
        msg.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    
    # Установка красивого шрифта
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = XillenFileFinder()
    window.show()
    sys.exit(app.exec())
