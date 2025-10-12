import sys
from gui.main_window import WerewolfApp
import tkinter as tk

def main():
    root = tk.Tk()
    app = WerewolfApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
