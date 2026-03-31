from .styles import get_theme, DARK_THEME, LIGHT_THEME

# Lazy imports: these modules have heavy dependencies (PyQt5, LLM providers)
# Import them only when explicitly accessed to avoid import chain failures
# when running in restricted environments (e.g. LO embedded Python).

def __getattr__(name):
    if name == "ChatWidget":
        from .chat_widget import ChatWidget
        return ChatWidget
    elif name == "SettingsDialog":
        from .settings_dialog import SettingsDialog
        return SettingsDialog
    elif name == "HelpDialog":
        from .help_dialog import HelpDialog
        return HelpDialog
    elif name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "get_theme",
    "DARK_THEME",
    "LIGHT_THEME",
    "ChatWidget",
    "SettingsDialog",
    "HelpDialog",
    "MainWindow",
]
