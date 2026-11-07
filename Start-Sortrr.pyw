#! python3
"""Windows GUI launcher for Sortrr."""
import ctypes
import logging
import os
from logging.handlers import RotatingFileHandler
from app_paths import APP_DIR, FROZEN, data_directory


def start():
    log_path = data_directory() / "sortrr.log"
    try:
        os.chdir(APP_DIR)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_path, maxBytes=512_000, backupCount=2, encoding="utf-8")
        logging.basicConfig(
            level=logging.INFO, handlers=[handler],
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
        from qt_app import main

        def log_qt_message(kind, context, message):
            level = {
                QtMsgType.QtDebugMsg: logging.DEBUG,
                QtMsgType.QtInfoMsg: logging.INFO,
                QtMsgType.QtWarningMsg: logging.WARNING,
                QtMsgType.QtCriticalMsg: logging.ERROR,
                QtMsgType.QtFatalMsg: logging.CRITICAL,
            }.get(kind, logging.WARNING)
            logging.getLogger("qt").log(level, message)

        qInstallMessageHandler(log_qt_message)
        logging.getLogger("sortrr").info("Starting Sortrr")
        result = main()
        if result == 0:
            return 0
        message = f"Sortrr could not open its window.\n\nSee {log_path} for details."
    except ModuleNotFoundError as error:
        logging.getLogger("sortrr").exception("Startup dependency missing")
        if error.name == "PySide6" and not FROZEN:
            message = "Sortrr needs Qt for Python. Install the packages listed in requirements.txt and reopen Sortrr."
        else:
            message = f"Sortrr could not start.\n\nSee {log_path} for details."
    except Exception as error:
        logging.getLogger("sortrr").exception("Startup failed")
        message = f"Sortrr could not start.\n\n{error}\n\nLog: {log_path}"
    ctypes.windll.user32.MessageBoxW(None, message, "Sortrr", 0x10)
    return 1


if __name__ == "__main__":
    raise SystemExit(start())
