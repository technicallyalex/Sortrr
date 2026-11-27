"""Opt-in, per-user Windows login startup for the portable app."""
import os
import sys
from pathlib import Path
from app_paths import FROZEN

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Sortrr"


def supported():
    return os.name == "nt" and FROZEN


def startup_command(executable=None):
    path = Path(executable or sys.executable).resolve()
    command = f'"{path}" --startup'
    if len(command) > 260:
        raise ValueError("Move Sortrr to a shorter folder path before enabling Windows startup.")
    return command


def enabled(registry=None):
    if os.name != "nt" and registry is None:
        return False
    if registry is None:
        import winreg as registry
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_READ) as key:
            value, kind = registry.QueryValueEx(key, VALUE_NAME)
        return kind == registry.REG_SZ and bool(value)
    except FileNotFoundError:
        return False


def set_enabled(enable, registry=None, executable=None):
    if registry is None:
        if not supported():
            raise ValueError("Open the packaged Windows app to configure Windows startup.")
        import winreg as registry
    if enable:
        command = startup_command(executable)
        with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
            registry.SetValueEx(key, VALUE_NAME, 0, registry.REG_SZ, command)
    else:
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                registry.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
