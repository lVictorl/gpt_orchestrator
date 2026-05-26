"""
gui/history_panel.py — HistoryPanel v2

Исправления:
  - Чаты сгруппированы по проектам (QTreeWidget)
  - Внутри проекта: папки Анализ / Код / Тесты / Критика / Прочее
  - Клик на чат → открывает его историю (chat_selected сигнал)
  - Главный чат проекта (первый по времени) выделяется
  - Поддержка collapse/expand папок
  - Кнопка «🏠 Главный чат» возвращает в первый чат проекта
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMenu, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from storage.models import ChatMeta, ProjectMeta

# Категория → иконка заголовка папки
_CATEGORY_ICONS = {
    "critique": "🔍 Критика & Анализ",
    "tests":    "🧪 Тесты",
    "spec":     "📐 Спецификация",
    "code":     "💻 Код",
    "other":    "💬 Прочее",
}

_CATEGORY_ORDER = ["critique", "tests", "spec", "code", "other"]


class HistoryPanel(QWidget):
    """Левая боковая панель с деревом проектов и чатов."""

    chat_selected      = pyqtSignal(str)        # chat_id
    chat_deleted       = pyqtSignal(str)        # chat_id
    chat_renamed       = pyqtSignal(str, str)   # chat_id, new_title
    new_chat_requested = pyqtSignal()
    home_requested     = pyqtSignal()           # вернуться в главный чат проекта

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(340)
        # Внутренние данные: project_id -> list[ChatMeta]
        self._project_chats: Dict[str, List[ChatMeta]] = {}
        self._projects: List[ProjectMeta] = []
        self._orphan_chats: List[ChatMeta] = []   # чаты без проекта
        self._first_chat_id: Optional[str] = None  # первый чат последнего проекта
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(6)

        # Заголовок
        header_row = QHBoxLayout()
        title = QLabel("📁 Проекты")
        title.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #8b949e; "
            "text-transform: uppercase; letter-spacing: 1px;"
        )
        header_row.addWidget(title)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Поиск
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Поиск чата...")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        # Дерево
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(14)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background: #0d1117;
                border: none;
                color: #c9d1d9;
            }
            QTreeWidget::item {
                padding: 4px 2px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background: #1c4a8f;
                color: #e6edf3;
            }
            QTreeWidget::item:hover {
                background: #21262d;
            }
            QTreeWidget::branch {
                background: #0d1117;
            }
        """)
        layout.addWidget(self._tree, stretch=1)

        # Кнопки
        btn_row = QHBoxLayout()
        self._new_btn = QPushButton("+ Чат")
        self._new_btn.setToolTip("Создать новый чат")
        self._new_btn.clicked.connect(self.new_chat_requested.emit)
        btn_row.addWidget(self._new_btn)

        self._home_btn = QPushButton("🏠")
        self._home_btn.setToolTip("Вернуться в главный чат проекта")
        self._home_btn.setFixedWidth(36)
        self._home_btn.clicked.connect(self._go_home)
        btn_row.addWidget(self._home_btn)

        layout.addLayout(btn_row)

    # ── Public API ─────────────────────────────────────────

    def load_projects(
        self,
        projects: List[ProjectMeta],
        project_chats: Dict[str, List[ChatMeta]],
        orphan_chats: List[ChatMeta] | None = None,
    ) -> None:
        """Полная загрузка дерева: проекты + их чаты."""
        self._projects = projects
        self._project_chats = project_chats
        self._orphan_chats = orphan_chats or []
        self._rebuild_tree()

    def load_chats(self, chats: List[ChatMeta]) -> None:
        """Устаревший метод: отображает чаты без группировки."""
        self._orphan_chats = chats
        self._rebuild_tree()

    def add_chat(self, chat: ChatMeta) -> None:
        if chat.project_id:
            if chat.project_id not in self._project_chats:
                self._project_chats[chat.project_id] = []
            self._project_chats[chat.project_id].append(chat)
        else:
            self._orphan_chats.append(chat)
        self._rebuild_tree()

    def remove_chat(self, chat_id: str) -> None:
        for pid, chats in self._project_chats.items():
            self._project_chats[pid] = [c for c in chats if c.chat_id != chat_id]
        self._orphan_chats = [c for c in self._orphan_chats if c.chat_id != chat_id]
        self._rebuild_tree()

    def rename_chat(self, chat_id: str, title: str) -> None:
        for chats in self._project_chats.values():
            for c in chats:
                if c.chat_id == chat_id:
                    c.title = title
        for c in self._orphan_chats:
            if c.chat_id == chat_id:
                c.title = title
        self._rebuild_tree()

    def select_chat(self, chat_id: str) -> None:
        if not chat_id:
            self._tree.clearSelection()
            return
        def _find(node: QTreeWidgetItem) -> bool:
            cid = node.data(0, Qt.ItemDataRole.UserRole)
            if cid == chat_id:
                self._tree.setCurrentItem(node)
                node.parent() and node.parent().setExpanded(True)
                return True
            for i in range(node.childCount()):
                if _find(node.child(i)):
                    return True
            return False
        for i in range(self._tree.topLevelItemCount()):
            _find(self._tree.topLevelItem(i))

    # ── Tree building ─────────────────────────────────────

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        self._first_chat_id = None

        # 1) Проекты со своими чатами
        for project in self._projects:
            chats = self._project_chats.get(project.project_id, [])
            proj_item = self._make_project_item(project, chats)
            self._tree.addTopLevelItem(proj_item)
            proj_item.setExpanded(True)

        # 2) Осиротевшие чаты (без проекта) — в конце
        if self._orphan_chats:
            orphan_root = QTreeWidgetItem(["💬 Чаты"])
            orphan_root.setFont(0, self._section_font())
            orphan_root.setForeground(0, self._tree.palette().mid())
            orphan_root.setFlags(orphan_root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for chat in self._orphan_chats:
                orphan_root.addChild(self._make_chat_item(chat))
            self._tree.addTopLevelItem(orphan_root)
            orphan_root.setExpanded(True)

    def _make_project_item(
        self, project: ProjectMeta, chats: List[ChatMeta]
    ) -> QTreeWidgetItem:
        score_str = f" [{project.critique_score}/100]" if project.critique_score is not None else ""
        status_icon = {"done": "✅", "in_progress": "⚙️", "error": "❌"}.get(project.status, "📁")
        label = f"{status_icon} {project.title or project.project_id[:8]}{score_str}"
        item = QTreeWidgetItem([label])
        item.setFont(0, self._project_font())
        item.setToolTip(0, f"ID: {project.project_id}\nТип: {project.task_type}\n{project.created_at.strftime('%Y-%m-%d %H:%M')}")
        # Нет UserRole — это не кликабельный чат
        item.setData(0, Qt.ItemDataRole.UserRole, None)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, project.project_id)

        # Группировка по категориям
        categories: Dict[str, List[ChatMeta]] = {k: [] for k in _CATEGORY_ORDER}
        for chat in chats:
            cat = chat.stage_category or "other"
            if cat not in categories:
                cat = "other"
            categories[cat].append(chat)

        first_set = False
        for cat_key in _CATEGORY_ORDER:
            cat_chats = categories[cat_key]
            if not cat_chats:
                continue
            cat_item = QTreeWidgetItem([_CATEGORY_ICONS.get(cat_key, cat_key)])
            cat_item.setFont(0, self._category_font())
            cat_item.setForeground(0, self._tree.palette().mid())
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            cat_item.setData(0, Qt.ItemDataRole.UserRole, None)
            for chat in cat_chats:
                chat_item = self._make_chat_item(chat)
                cat_item.addChild(chat_item)
                if not first_set:
                    self._first_chat_id = chat.chat_id
                    first_set = True
            item.addChild(cat_item)
            cat_item.setExpanded(True)

        # Если нет категорий — добавить чаты напрямую
        if not any(categories.values()):
            for chat in chats:
                item.addChild(self._make_chat_item(chat))

        return item

    def _make_chat_item(self, chat: ChatMeta) -> QTreeWidgetItem:
        msg_count = f" ({chat.message_count})" if chat.message_count else ""
        label = f"💬 {chat.title}{msg_count}"
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, chat.chat_id)
        item.setToolTip(0, f"ID: {chat.chat_id}\n{chat.created_at.strftime('%Y-%m-%d %H:%M')}")
        return item

    @staticmethod
    def _project_font() -> QFont:
        f = QFont()
        f.setBold(True)
        f.setPointSize(12)
        return f

    @staticmethod
    def _category_font() -> QFont:
        f = QFont()
        f.setPointSize(10)
        f.setItalic(True)
        return f

    @staticmethod
    def _section_font() -> QFont:
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        return f

    # ── Event handlers ─────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        chat_id = item.data(0, Qt.ItemDataRole.UserRole)
        if chat_id:
            self.chat_selected.emit(chat_id)

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if not item:
            return
        chat_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not chat_id:
            return
        menu = QMenu(self)
        rename_act = menu.addAction("✏️ Переименовать")
        menu.addSeparator()
        delete_act = menu.addAction("🗑 Удалить")
        action = menu.exec(self._tree.mapToGlobal(pos))
        if action == rename_act:
            new_title, ok = QInputDialog.getText(
                self, "Переименовать", "Новое название:", text=item.text(0).replace("💬 ", "")
            )
            if ok and new_title.strip():
                self.chat_renamed.emit(chat_id, new_title.strip())
        elif action == delete_act:
            self.chat_deleted.emit(chat_id)

    def _go_home(self) -> None:
        """Открыть первый чат последнего проекта."""
        if self._first_chat_id:
            self.chat_selected.emit(self._first_chat_id)
            self.select_chat(self._first_chat_id)
        else:
            self.home_requested.emit()

    def _filter(self, text: str) -> None:
        text = text.lower()
        def _set_hidden(node: QTreeWidgetItem, parent_matches: bool) -> bool:
            """Возвращает True если хотя бы один потомок виден."""
            my_text = node.text(0).lower()
            matches = text in my_text or parent_matches
            any_child_visible = False
            for i in range(node.childCount()):
                child_visible = _set_hidden(node.child(i), matches)
                any_child_visible = any_child_visible or child_visible
            visible = matches or any_child_visible
            node.setHidden(not visible)
            return visible
        for i in range(self._tree.topLevelItemCount()):
            _set_hidden(self._tree.topLevelItem(i), False)
