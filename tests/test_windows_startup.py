import unittest
from pathlib import Path
from windows_startup import enabled, set_enabled, startup_command, VALUE_NAME, RUN_KEY


class Registry:
    HKEY_CURRENT_USER = 1
    KEY_READ = 2
    KEY_SET_VALUE = 4
    REG_SZ = 1

    def __init__(self):
        self.values = {"Other app": ("untouched", self.REG_SZ)}
        self.denied = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def OpenKey(self, hive, path, *args):
        if self.denied:
            raise PermissionError("Denied")
        assert hive == self.HKEY_CURRENT_USER and path == RUN_KEY
        return self

    CreateKeyEx = OpenKey

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class WindowsStartupTests(unittest.TestCase):
    def test_command_quotes_portable_path_with_spaces(self):
        command = startup_command(Path("C:/Portable Apps/Sortrr/Sortrr.exe"))
        self.assertTrue(command.startswith('"'))
        self.assertTrue(command.endswith('Sortrr.exe" --startup'))

    def test_enable_and_disable_only_our_entry(self):
        registry = Registry()
        self.assertFalse(enabled(registry))
        set_enabled(True, registry, "C:/Apps/Sortrr.exe")
        self.assertTrue(enabled(registry))
        self.assertIn("--startup", registry.values[VALUE_NAME][0])
        set_enabled(False, registry)
        set_enabled(False, registry)
        self.assertFalse(enabled(registry))
        self.assertEqual(registry.values, {"Other app": ("untouched", registry.REG_SZ)})

    def test_permission_failure_is_not_reported_as_success(self):
        registry = Registry()
        registry.denied = True
        with self.assertRaises(PermissionError):
            set_enabled(True, registry, "C:/Apps/Sortrr.exe")
        self.assertNotIn(VALUE_NAME, registry.values)
