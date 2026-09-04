import ctypes
import platform
import sys
import tkinter as tk

print("VIER-NEX - Diagnostico de render")
print("=" * 52)
print("Windows:", platform.platform())
print("Python:", sys.version.replace("\n", " "))

try:
    import customtkinter as ctk
    print("CustomTkinter:", getattr(ctk, "__version__", "desconocida"))
except Exception as exc:
    print("CustomTkinter: ERROR", exc)

root = tk.Tk()
root.withdraw()
try:
    print("Tk:", root.tk.call("info", "patchlevel"))
    print("Pantalla:", f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}")
finally:
    root.destroy()

try:
    user32 = ctypes.windll.user32
    if hasattr(user32, "GetDpiForSystem"):
        dpi = int(user32.GetDpiForSystem())
        print("DPI sistema:", dpi)
        print("Escala aproximada:", f"{dpi / 96 * 100:.0f}%")
except Exception as exc:
    print("DPI: no disponible", exc)
