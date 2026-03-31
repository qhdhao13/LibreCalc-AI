"""LibreOffice Script Provider entry point.

This module bridges LibreOffice's Script Framework to the real CalcAI application.
Instead of importing PyQt5 directly (which is unavailable in LO's embedded Python),
it starts an HTTP bridge server and launches the PyQt5 UI in a separate system
Python subprocess.
"""

import sys
import os
import logging
import subprocess
import json
import threading
import traceback

logger = logging.getLogger("CalcAI.interface")

# --- Path Setup ---
_this_file = globals().get('__file__') or sys._getframe().f_code.co_filename
_script_dir = os.path.dirname(os.path.abspath(_this_file))
_calcai_dir = os.path.join(_script_dir, "CalcAI")

if _calcai_dir not in sys.path:
    sys.path.insert(0, _calcai_dir)

# --- Log file for debugging (always write to file) ---
_log_dir = os.path.join(os.path.expanduser("~"), ".config", "libre_calc_ai", "logs")
try:
    os.makedirs(_log_dir, exist_ok=True)
except Exception:
    _log_dir = os.path.expanduser("~")

_log_file = os.path.join(_log_dir, "oxt_bridge.log")


def _log(msg):
    """Write a log line to the debug log file."""
    try:
        with open(_log_file, "a", encoding="utf-8") as f:
            import datetime
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


_log(f"interface.py loaded. _calcai_dir={_calcai_dir}")

# --- Global state ---
_bridge_server = None
_subprocess = None
_subprocess_lock = threading.Lock()
_cached_python_path = None  # Cache to avoid running 'where' every time


def _get_desktop_from_context():
    """Get LibreOffice Desktop from the script execution context."""
    try:
        ctx = XSCRIPTCONTEXT.getComponentContext()
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        return ctx, desktop
    except Exception as e:
        _log(f"_get_desktop_from_context error: {e}")
        return None, None


def _create_dispatcher():
    """Create ToolDispatcher with injected UNO context."""
    try:
        ctx, desktop = _get_desktop_from_context()
        if not ctx or not desktop:
            _log("WARNING: Could not get UNO context")
            return None, None

        from core.uno_bridge import LibreOfficeBridge
        from core.cell_inspector import CellInspector
        from core.cell_manipulator import CellManipulator
        from core.sheet_analyzer import SheetAnalyzer
        from core.error_detector import ErrorDetector
        from llm.tool_definitions import ToolDispatcher

        bridge = LibreOfficeBridge()
        bridge._local_context = ctx
        bridge._context = ctx
        bridge._desktop = desktop
        bridge._connected = True

        inspector = CellInspector(bridge)
        manipulator = CellManipulator(bridge)
        analyzer = SheetAnalyzer(bridge)
        detector = ErrorDetector(bridge, inspector)
        dispatcher = ToolDispatcher(inspector, manipulator, analyzer, detector)

        _log("UNO dispatcher created OK")
        return bridge, dispatcher

    except Exception as e:
        _log(f"_create_dispatcher error: {e}\n{traceback.format_exc()}")
        return None, None


def _build_context_func(bridge):
    """Create a context function that returns sheet summary + selection info."""
    def context_func():
        result = {}
        try:
            from core.sheet_analyzer import SheetAnalyzer
            analyzer = SheetAnalyzer(bridge)
            summary = analyzer.get_sheet_summary()
            result["sheet_name"] = summary.get("sheet_name", "")
            result["used_range"] = summary.get("used_range", "")
            result["row_count"] = summary.get("row_count", 0)
            result["col_count"] = summary.get("col_count", 0)
            result["headers"] = summary.get("headers", [])
        except Exception as e:
            _log(f"context sheet summary error: {e}")

        try:
            from core.uno_bridge import LibreOfficeBridge
            doc = bridge.get_active_document()
            controller = doc.getCurrentController()
            selection = controller.getSelection()
            address = LibreOfficeBridge.get_selection_address(selection)
            result["selection"] = address
        except Exception as e:
            _log(f"context selection error: {e}")

        return result
    return context_func


def _find_system_python():
    """Find system Python executable (with PyQt5 support). Cached after first call."""
    global _cached_python_path
    if _cached_python_path and os.path.isfile(_cached_python_path):
        return _cached_python_path

    found = _find_system_python_uncached()

    # On Windows prefer pythonw.exe (no console window)
    if sys.platform == "win32" and found.endswith("python.exe"):
        pythonw = found.replace("python.exe", "pythonw.exe")
        if os.path.isfile(pythonw):
            found = pythonw

    _cached_python_path = found
    _log(f"Python path cached: {found}")
    return found


def _find_system_python_uncached():
    """Actually search for system Python."""
    # 1. Check settings file for user-configured path
    try:
        config_file = os.path.join(
            os.path.expanduser("~"), ".config", "libre_calc_ai", "settings.json"
        )
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                settings = json.load(f)
            custom_path = settings.get("system_python_path", "")
            if custom_path and os.path.isfile(custom_path):
                _log(f"Using custom python: {custom_path}")
                return custom_path
    except Exception:
        pass

    # 2. Windows: check common paths FIRST (faster than 'where')
    if sys.platform == "win32":
        home = os.path.expanduser("~")
        # Most common location: AppData\Local\Programs\Python
        local_programs = os.path.join(home, "AppData", "Local", "Programs", "Python")
        if os.path.isdir(local_programs):
            for sub in sorted(os.listdir(local_programs), reverse=True):
                candidate = os.path.join(local_programs, sub, "python.exe")
                if os.path.isfile(candidate):
                    _log(f"Found python (fast path): {candidate}")
                    return candidate

        # Root-level installs
        for ver in ("313", "312", "311", "310", "39"):
            candidate = f"C:\\Python{ver}\\python.exe"
            if os.path.isfile(candidate):
                _log(f"Found python (root): {candidate}")
                return candidate

        # Fallback: 'where' command (slower)
        skip_patterns = ("LibreOffice", "WindowsApps")
        try:
            result = subprocess.run(
                ["where", "python"],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    path = line.strip()
                    if any(skip in path for skip in skip_patterns):
                        continue
                    if os.path.isfile(path):
                        _log(f"Found python via where: {path}")
                        return path
        except Exception as e:
            _log(f"where python failed: {e}")
    else:
        for cmd in ("python3", "python"):
            try:
                result = subprocess.run(
                    ["which", cmd],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    path = result.stdout.strip()
                    if os.path.isfile(path):
                        return path
            except Exception:
                continue

    _log("WARNING: No system python found, falling back to 'python'")
    return "python"


def _build_clean_env(python_path, port):
    """Build a clean environment for the subprocess."""
    python_dir = os.path.dirname(python_path)
    env = {}

    # Copy only safe env vars
    safe_keys = {
        "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP",
        "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "USERNAME",
        "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMPUTERNAME",
        "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
        "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
        "PROGRAMFILES", "PROGRAMFILES(X86)",
        "PATHEXT", "COMSPEC",
    }
    for key, val in os.environ.items():
        if key.upper() in safe_keys:
            env[key] = val

    # Clean PATH: Python dir + system dirs only (NO LibreOffice)
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    env["PATH"] = ";".join([
        python_dir,
        os.path.join(python_dir, "Scripts"),
        system_root,
        os.path.join(system_root, "System32"),
        os.path.join(system_root, "System32", "Wbem"),
    ])

    env["CALCAI_BRIDGE_PORT"] = str(port)

    # Qt plugin path
    for qt_sub in ("Qt5", "Qt"):
        qt_path = os.path.join(python_dir, "Lib", "site-packages", "PyQt5", qt_sub, "plugins")
        if os.path.isdir(qt_path):
            env["QT_PLUGIN_PATH"] = qt_path
            break

    return env


def _start_bridge_and_subprocess(mode="assistant"):
    """Start bridge server and launch system Python subprocess.

    This function is designed to return as fast as possible.
    Heavy work (dispatcher creation) happens AFTER the subprocess is launched.
    """
    global _bridge_server, _subprocess

    with _subprocess_lock:
        # If subprocess is already running
        if _subprocess is not None and _subprocess.poll() is None:
            _log(f"Subprocess already running (pid={_subprocess.pid})")
            return

        _log(f"=== Starting bridge for mode={mode} ===")

        # Step 1: Find python (cached, instant on 2nd+ call)
        python_path = _find_system_python()
        _log(f"System python: {python_path}")

        # Step 2: Start bridge server IMMEDIATELY (no dispatcher yet)
        from core.bridge_server import BridgeServer
        _bridge_server = BridgeServer(dispatcher=None, context_func=None)
        port = _bridge_server.start()
        _log(f"Bridge server started on port {port}")

        # Step 3: Launch subprocess IMMEDIATELY
        main_py = os.path.join(_calcai_dir, "main.py")
        cmd = [python_path, main_py, "--bridge-port", str(port)]
        if mode == "settings":
            cmd.append("--show-settings")
        elif mode == "about":
            cmd.append("--show-about")

        env = _build_clean_env(python_path, port)
        stderr_log = os.path.join(_log_dir, "subprocess_stderr.log")

        try:
            stderr_file = open(stderr_log, "w", encoding="utf-8")
            _subprocess = subprocess.Popen(
                cmd,
                env=env,
                cwd=_calcai_dir,
                stderr=stderr_file,
                stdout=subprocess.PIPE,
            )
            _log(f"Subprocess launched (pid={_subprocess.pid})")
        except Exception as e:
            _log(f"FAILED to launch subprocess: {e}\n{traceback.format_exc()}")
            if _bridge_server:
                _bridge_server.stop()
                _bridge_server = None
            raise

    # Step 4: Create dispatcher in background (doesn't block LO)
    def _setup_and_monitor():
        global _bridge_server, _subprocess
        try:
            # Create dispatcher now (while subprocess is starting up)
            bridge, dispatcher = _create_dispatcher()
            if _bridge_server and dispatcher:
                _bridge_server.set_dispatcher(dispatcher)
                context_func = _build_context_func(bridge)
                _bridge_server.set_context_func(context_func)
                _log("Dispatcher attached to bridge server")

            # Monitor subprocess
            if _subprocess:
                retcode = _subprocess.wait()
                _log(f"Subprocess exited with code {retcode}")

                try:
                    stderr_file.close()
                    with open(stderr_log, "r", encoding="utf-8") as f:
                        err_output = f.read().strip()
                    if err_output:
                        _log(f"Subprocess stderr:\n{err_output}")
                except Exception:
                    pass

        except Exception as e:
            _log(f"Setup/monitor error: {e}\n{traceback.format_exc()}")
        finally:
            if _bridge_server:
                _bridge_server.stop()
                _bridge_server = None
            _subprocess = None

    threading.Thread(target=_setup_and_monitor, daemon=True, name="BridgeSetup").start()


def show_assistant(*args):
    """Open the AI Assistant main window."""
    try:
        _start_bridge_and_subprocess(mode="assistant")
    except Exception as e:
        _log(f"show_assistant error: {e}\n{traceback.format_exc()}")
        _show_error(f"AI Asistan acilamadi:\n{e}")


def show_settings(*args):
    """Open the settings dialog."""
    try:
        _start_bridge_and_subprocess(mode="settings")
    except Exception as e:
        _log(f"show_settings error: {e}\n{traceback.format_exc()}")
        _show_error(f"Ayarlar acilamadi:\n{e}")


def show_about(*args):
    """Show the help/about dialog."""
    try:
        _start_bridge_and_subprocess(mode="about")
    except Exception as e:
        _log(f"show_about error: {e}\n{traceback.format_exc()}")
        _show_error(f"Hakkinda gosterilemedi:\n{e}")


def _show_error(message):
    """Show error using LibreOffice UNO message box as fallback."""
    try:
        import uno
        ctx = XSCRIPTCONTEXT.getComponentContext()
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        frame = desktop.getCurrentFrame()
        window = frame.getContainerWindow()
        toolkit = window.getToolkit()

        from com.sun.star.awt.MessageBoxType import ERRORBOX
        box = toolkit.createMessageBox(window, ERRORBOX, 1, "CalcAI Hata", message)
        box.execute()
    except Exception:
        print(f"CalcAI ERROR: {message}", file=sys.stderr)


# Export scripts for the Script Provider
g_exportedScripts = (show_assistant, show_settings, show_about)
