"""Launch Sortrr on the desktop."""

if __name__ == "__main__":
    try:
        from qt_app import main
    except ModuleNotFoundError as exc:
        if exc.name != "PySide6":
            raise
        raise SystemExit("Sortrr needs Qt for Python. Run: python -m pip install -r requirements.txt")
    raise SystemExit(main())
