import sys
import tkinter as tk
from gui.main_window import WerewolfApp

# Windows 高 DPI 清晰度提升（可忽略异常）
try:
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

def main():
    root = tk.Tk()
    app = WerewolfApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
