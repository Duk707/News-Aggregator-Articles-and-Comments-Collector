"""
Main Application Launcher for Adaptive News Article and Comment Collector.
Launches the Tkinter Desktop GUI application.
"""
import os
import sys
import multiprocessing
import tkinter as tk

# PyInstaller frozen application path & environment initialization
if getattr(sys, 'frozen', False):
    # Redirect missing stdio streams to os.devnull for windowed GUI mode (console=False)
    if sys.stdout is None or getattr(sys.stdout, 'fileno', lambda: -1)() < 0:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None or getattr(sys.stderr, 'fileno', lambda: -1)() < 0:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdin is None or getattr(sys.stdin, 'fileno', lambda: -1)() < 0:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")

    # Resolve PyInstaller temporary extraction directory for bundled Playwright browsers
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
    bundled_browsers = os.path.join(base_dir, "ms-playwright")
    if os.path.exists(bundled_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browsers

    # Set working directory to the executable's directory so output persists next to the EXE
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(exe_dir)

from src.gui.app import CollectionApp

def main():
    """Launches the Desktop Application GUI."""
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = CollectionApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()



