"""Panel de escritorio (tkinter, stdlib): ver trabajos enviados.

Read-only sobre el historial + lista de impresoras, con botón para
disparar un remito de prueba. Sin dependencias extra.
"""
from __future__ import annotations

import logging
import queue
import threading
import types

log = logging.getLogger(__name__)
REFRESH_MS = 3000


def run_panel(hpath=None, default_printer: str = "") -> int:
    """Abre la ventana. Retorna código de salida."""
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:
        print("ERROR: tkinter no disponible en este Python", flush=True)
        return 2

    from . import windows_print
    from .print_history import history_path_for, read_recent

    if hpath is None:
        hpath = history_path_for("", "")

    root = tk.Tk()
    root.title("FASA Print Agent — trabajos")
    root.geometry("900x520")

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Impresora:").pack(side="left")
    try:
        printers = windows_print.list_printers()
    except Exception as e:  # noqa: BLE001
        printers = []
        log.warning("list_printers: %s", e)
    printer_var = tk.StringVar(value=default_printer or (printers[0] if printers else ""))
    combo = ttk.Combobox(top, textvariable=printer_var, values=printers,
                         width=40, state="readonly" if printers else "normal")
    combo.pack(side="left", padx=6)
    status_var = tk.StringVar(value="Listo.")
    jobs_q: queue.Queue = queue.Queue()

    def do_print_test():
        from .remito_cli import cmd_print_test

        printer = printer_var.get().strip()
        if not printer:
            messagebox.showwarning("Falta impresora", "Elegí una impresora.")
            return
        status_var.set(f"Imprimiendo en {printer}...")
        btn_print.config(state="disabled")

        def _run():
            ns = types.SimpleNamespace(
                remito_json=None, layout_json=None, offset_x=None,
                offset_y=None, out="remito-test.pdf", printer=printer,
                copies=1, dpi=300, dc_mode="auto", no_print=False,
                print_remito_pdf=None,
            )
            try:
                rc = cmd_print_test(ns, hpath)
                jobs_q.put(("ok" if rc == 0 else "error",
                            f"Remito test rc={rc}"))
            except Exception as e:  # noqa: BLE001
                jobs_q.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    btn_print = ttk.Button(top, text="Imprimir remito test", command=do_print_test)
    btn_print.pack(side="left", padx=6)
    ttk.Button(top, text="Actualizar", command=lambda: refresh(force=True)).pack(side="left")
    ttk.Label(root, textvariable=status_var, padding=(8, 0)).pack(fill="x")

    cols = ("ts", "doc", "printer", "copies", "result", "job", "error")
    tree = ttk.Treeview(root, columns=cols, show="headings", height=18)
    widths = {"ts": 130, "doc": 220, "printer": 200, "copies": 60,
              "result": 70, "job": 70, "error": 300}
    for c in cols:
        tree.heading(c, text=c.upper())
        tree.column(c, width=widths[c], anchor="w")
    tree.pack(fill="both", expand=True, padx=8, pady=8)

    last_count = {"n": -1}

    def refresh(force=False):
        try:
            while True:
                kind, msg = jobs_q.get_nowait()
                status_var.set(msg)
                if kind == "ok":
                    btn_print.config(state="normal")
                else:
                    btn_print.config(state="normal")
                    if kind == "error":
                        messagebox.showerror("Impresión", msg)
        except queue.Empty:
            pass
        rows = read_recent(hpath, 200)
        if force or len(rows) != last_count["n"]:
            last_count["n"] = len(rows)
            tree.delete(*tree.get_children())
            for r in rows:
                tree.insert("", "end", values=(
                    r.get("ts", ""), r.get("doc", ""),
                    r.get("printer", ""), r.get("copies", ""),
                    r.get("result", ""), r.get("windows_job_id", ""),
                    r.get("error", r.get("code", "")),
                ))
            n_ok = sum(1 for r in rows if r.get("result") == "OK")
            n_err = sum(1 for r in rows if r.get("result") == "ERROR")
            if not status_var.get().startswith("Imprimiendo"):
                status_var.set(f"{len(rows)} trabajos (OK={n_ok} ERROR={n_err})")
        root.after(REFRESH_MS, refresh)

    refresh(force=True)
    root.mainloop()
    return 0
