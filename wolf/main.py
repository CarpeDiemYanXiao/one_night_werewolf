import sys

# Windows 高 DPI 清晰度提升（可忽略异常）
try:
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

def _run_qt():
    from PySide6 import QtWidgets
    from gui.qt_main_window import QtWerewolfApp
    app = QtWidgets.QApplication(sys.argv)
    w = QtWerewolfApp()
    w.resize(1000, 720)
    w.show()
    sys.exit(app.exec())


def _run_tk():
    import tkinter as tk
    from gui.main_window import WerewolfApp
    root = tk.Tk()
    app = WerewolfApp(root)
    root.mainloop()


def main():
    # 优先尝试 Qt，失败则回退 Tk
    try:
        import PySide6  # noqa: F401
        _run_qt()
    except Exception:
        _run_tk()

if __name__ == '__main__':
    main()
