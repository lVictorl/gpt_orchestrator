"""
gui/dialogs/api_key_dialog.py — ApiKeyDialog + SettingsDialog v1.4

Новое:
  - Кнопка «🔗 Проверить соединение» — вызывает AIGateway.ping()
  - DeepSeek: предупреждение о частоте запросов
  - SettingsDialog: все настройки редактируемы
"""
from __future__ import annotations

import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


class PingWorker(QThread):
    """Выполняет AIGateway.ping() в фоне, чтобы не блокировать UI."""
    result_ready = pyqtSignal(bool, str)

    def __init__(self, gateway, provider: str, key: str, config) -> None:
        super().__init__()
        self._gateway = gateway
        self._provider = provider
        self._key = key
        self._config = config

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            # Временно применить ключ для теста
            self._gateway.set_api_key(self._key, self._provider)
            ok, msg = loop.run_until_complete(self._gateway.ping())
            self.result_ready.emit(ok, msg)
        except Exception as exc:
            self.result_ready.emit(False, f"❌ {exc}")
        finally:
            loop.close()


class ApiKeyDialog(QDialog):
    """Диалог для ввода/изменения API-ключа с проверкой соединения."""

    def __init__(
        self,
        current_key: str = "",
        provider: str = "anthropic",
        ai_gateway=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._gateway = ai_gateway
        self._ping_worker: Optional[PingWorker] = None
        self.setWindowTitle("🔑 API-ключ")
        self.setMinimumWidth(500)
        self.setMinimumHeight(320)
        self.setModal(True)
        self._setup_ui(current_key, provider)

    def _setup_ui(self, current_key: str, provider: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()

        # Провайдер
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["anthropic", "openai", "deepseek"])
        self._provider_combo.setCurrentText(provider)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        form.addRow("Провайдер:", self._provider_combo)

        # Поле ключа
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setText(current_key)
        self._key_edit.setPlaceholderText("sk-... / sk-ant-... / ключ DeepSeek")
        form.addRow("API-ключ:", self._key_edit)

        # Показать ключ
        self._show_cb = QCheckBox("Показать ключ")
        self._show_cb.toggled.connect(
            lambda c: self._key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password
            )
        )

        # Подсказка (DeepSeek)
        self._hint_label = QLabel()
        self._hint_label.setStyleSheet("color:#d29922;font-size:11px;")
        self._hint_label.setWordWrap(True)
        self._update_hint(provider)
        form.addRow("", self._hint_label)

        # Результат пинга
        self._ping_result = QLabel("")
        self._ping_result.setWordWrap(True)
        self._ping_result.setStyleSheet("font-size:12px;min-height:20px;")

        # Кнопка проверки
        self._ping_btn = QPushButton("🔗 Проверить соединение")
        self._ping_btn.clicked.connect(self._do_ping)

        layout.addLayout(form)
        layout.addWidget(self._show_cb)
        layout.addWidget(self._ping_btn)
        layout.addWidget(self._ping_result)

        note = QLabel("Ключ хранится локально в config.toml и никуда не передаётся.")
        note.setStyleSheet("color:#484f58;font-size:11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_provider_changed(self, provider: str) -> None:
        self._update_hint(provider)
        self._ping_result.setText("")

    def _update_hint(self, provider: str) -> None:
        hints = {
            "deepseek": (
                "⚠️ DeepSeek free-tier: 1 запрос в минуту.\n"
                "Программа автоматически делает паузу между запросами.\n"
                "Первый запрос начинается немедленно."
            ),
            "openai": "",
            "anthropic": "",
        }
        self._hint_label.setText(hints.get(provider, ""))

    def _do_ping(self) -> None:
        if self._gateway is None:
            self._ping_result.setText("⚠️ Gateway не инициализирован")
            self._ping_result.setStyleSheet("color:#d29922;font-size:12px;")
            return

        key = self._key_edit.text().strip()
        if not key:
            self._ping_result.setText("⚠️ Введите API-ключ")
            self._ping_result.setStyleSheet("color:#d29922;font-size:12px;")
            return

        provider = self._provider_combo.currentText()
        self._ping_btn.setEnabled(False)
        self._ping_btn.setText("⏳ Проверяю...")
        self._ping_result.setText("Отправляю тестовый запрос...")
        self._ping_result.setStyleSheet("color:#8b949e;font-size:12px;")

        # Нам нужна временная копия config для ping
        # Просто меняем ключ через gateway напрямую
        self._ping_worker = PingWorker(self._gateway, provider, key, None)
        self._ping_worker.result_ready.connect(self._on_ping_result)
        self._ping_worker.start()

    def _on_ping_result(self, ok: bool, message: str) -> None:
        self._ping_btn.setEnabled(True)
        self._ping_btn.setText("🔗 Проверить соединение")
        self._ping_result.setText(message)
        color = "#2ea043" if ok else "#da3633"
        self._ping_result.setStyleSheet(f"color:{color};font-size:12px;font-weight:bold;")

    @property
    def api_key(self) -> str:
        return self._key_edit.text().strip()

    @property
    def provider(self) -> str:
        return self._provider_combo.currentText()


class SettingsDialog(QDialog):
    """Диалог настроек — все параметры редактируемы."""

    def __init__(self, config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("⚙️ Настройки")
        self.setMinimumWidth(540)
        self.setMinimumHeight(480)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # API
        api_group = QGroupBox("API / Модели")
        api_form = QFormLayout(api_group)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["anthropic", "openai", "deepseek"])
        self._provider_combo.setCurrentText(
            self._config.get("api.provider", "anthropic")
        )
        api_form.addRow("Провайдер по умолчанию:", self._provider_combo)

        self._model_anthropic = QLineEdit(
            self._config.get("api.model_anthropic", "claude-sonnet-4-20250514")
        )
        api_form.addRow("Модель Anthropic:", self._model_anthropic)

        self._model_openai = QLineEdit(
            self._config.get("api.model_openai", "gpt-4o")
        )
        api_form.addRow("Модель OpenAI:", self._model_openai)

        # DeepSeek model selector with pricing
        try:
            from token_saver.token_optimizer import MODEL_PRICING
        except ImportError:
            MODEL_PRICING = {}
        deepseek_models = sorted([m for m in MODEL_PRICING if "deepseek" in m])
        self._model_deepseek = QComboBox()
        for m in deepseek_models:
            p = MODEL_PRICING.get(m, {"input": 0, "output": 0})
            label = f"{m}  [↑${p['input']:.2f}  ↓${p['output']:.2f} /1M tok]"
            self._model_deepseek.addItem(label, m)
        # Also allow custom model name
        self._model_deepseek.setEditable(True)
        # Set current
        cur_deepseek = self._config.get("api.model_deepseek", "deepseek-chat")
        found = False
        for i in range(self._model_deepseek.count()):
            if self._model_deepseek.itemData(i) == cur_deepseek:
                self._model_deepseek.setCurrentIndex(i)
                found = True
                break
        if not found:
            self._model_deepseek.setCurrentText(cur_deepseek)
        api_form.addRow("Модель DeepSeek:", self._model_deepseek)

        # Cost forecast label
        self._cost_preview_lbl = QLabel("")
        self._cost_preview_lbl.setStyleSheet("color:#8b949e;font-size:10px;")
        self._model_deepseek.currentIndexChanged.connect(self._update_cost_preview)
        self._update_cost_preview()
        api_form.addRow("", self._cost_preview_lbl)

        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(512, 32768)
        self._max_tokens.setSingleStep(512)
        self._max_tokens.setValue(self._config.get("api.max_tokens", 8192))
        api_form.addRow("Max tokens:", self._max_tokens)

        self._temperature = QDoubleSpinBox()
        self._temperature.setRange(0.0, 2.0)
        self._temperature.setSingleStep(0.05)
        self._temperature.setDecimals(2)
        self._temperature.setValue(self._config.get("api.temperature", 0.3))
        api_form.addRow("Temperature:", self._temperature)

        self._timeout = QSpinBox()
        self._timeout.setRange(10, 600)
        self._timeout.setSuffix(" сек")
        self._timeout.setValue(self._config.get("api.request_timeout", 120))
        api_form.addRow("Таймаут запроса:", self._timeout)

        self._rpm = QSpinBox()
        self._rpm.setRange(1, 120)
        self._rpm.setValue(self._config.get("api.rpm", 20))
        api_form.addRow("RPM (OpenAI/Anthropic):", self._rpm)

        # App
        app_group = QGroupBox("Приложение")
        app_form = QFormLayout(app_group)

        self._projects_dir = QLineEdit(
            self._config.get("app.projects_dir", "projects")
        )
        app_form.addRow("Папка проектов:", self._projects_dir)

        self._log_level_combo = QComboBox()
        self._log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._log_level_combo.setCurrentText(
            self._config.get("app.log_level", "INFO")
        )
        app_form.addRow("Уровень логирования:", self._log_level_combo)

        self._font_size = QSpinBox()
        self._font_size.setRange(10, 24)
        self._font_size.setValue(self._config.get("app.font_size", 13))
        app_form.addRow("Размер шрифта:", self._font_size)

        self._vim_mode_cb = QCheckBox("Vim-режим по умолчанию")
        self._vim_mode_cb.setChecked(self._config.get("app.vim_mode", True))
        app_form.addRow("", self._vim_mode_cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(api_group)
        layout.addWidget(app_group)
        layout.addWidget(buttons)

    def _update_cost_preview(self) -> None:
        """Show estimated cost per 1M tokens for selected DeepSeek model."""
        try:
            from token_saver.token_optimizer import MODEL_PRICING
            model_id = self._model_deepseek.currentData() or ""
            if not model_id:
                text = self._model_deepseek.currentText()
                model_id = text.split("[")[0].strip() if "[" in text else text.strip()
            p = MODEL_PRICING.get(model_id)
            if p:
                est_1k = (p["input"] + p["output"]) / 2 / 1000
                self._cost_preview_lbl.setText(
                    f"Примерная стоимость: ↑${p['input']:.3f} вход / ↓${p['output']:.3f} выход "
                    f"за 1M токенов | ≈${est_1k:.4f} за 1000 токенов"
                )
            else:
                self._cost_preview_lbl.setText("")
        except Exception:
            self._cost_preview_lbl.setText("")

    def _save_and_accept(self) -> None:
        self._config.set("api.provider",         self._provider_combo.currentText())
        self._config.set("api.model_anthropic",  self._model_anthropic.text().strip())
        self._config.set("api.model_openai",     self._model_openai.text().strip())
        ds_raw = (self._model_deepseek.currentData()
                   or self._model_deepseek.currentText().strip())
        # Strip the pricing label if present
        ds_model = ds_raw.split("[")[0].strip() if "[" in ds_raw else ds_raw.split("  ")[0].strip()
        self._config.set("api.model_deepseek", ds_model)
        self._config.set("api.max_tokens",       self._max_tokens.value())
        self._config.set("api.temperature",      self._temperature.value())
        self._config.set("api.request_timeout",  self._timeout.value())
        self._config.set("api.rpm",              self._rpm.value())
        self._config.set("app.projects_dir",     self._projects_dir.text().strip())
        self._config.set("app.log_level",        self._log_level_combo.currentText())
        self._config.set("app.font_size",        self._font_size.value())
        self._config.set("app.vim_mode",         self._vim_mode_cb.isChecked())
        try:
            self._config.save()
        except Exception:
            pass
        self.accept()
