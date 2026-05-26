"""gui/dialogs — диалоги приложения."""
from .api_key_dialog import ApiKeyDialog, SettingsDialog
from .project_wizard import ProjectWizardDialog
from .history_projects_dialog import HistoryProjectsDialog

__all__ = [
    "ApiKeyDialog",
    "SettingsDialog",
    "ProjectWizardDialog",
    "HistoryProjectsDialog",
]
