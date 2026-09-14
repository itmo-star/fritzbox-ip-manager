#!/usr/bin/env python3
"""
Fritz!Box IP-Manager & Tracker — Version 1.01
Elegante, symmetrische Benutzeroberfläche für macOS.
Verwendet FlatButton für garantierten Farbkontrast (keine macOS-Aqua Ausbleichung).
"""

import sys
import os
import time
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from fritz_service import FritzBoxClient, IPTracker, load_config, save_config, detect_fritzbox_host

APP_VERSION = "v1.01"

def notify_macos(title, message):
    """Sendet eine native macOS Systembenachrichtigung."""
    try:
        cmd = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", cmd], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

# Cupertino Dark-Slate Design-System
THEME = {
    "window_bg": "#181a1f",
    "card_bg": "#22252c",
    "card_border": "#313642",
    "input_bg": "#2b303a",
    "input_fg": "#ffffff",
    "input_border": "#3f4655",
    "text_primary": "#ffffff",
    "text_secondary": "#9ba3b4",
    "accent": "#0984e3",
    "accent_hover": "#00a8ff",
    "btn_bg": "#2c313c",
    "btn_hover": "#3a414f",
    "success": "#00b894",
    "warning": "#fdcb6e",
    "danger": "#ff7675",
    "zebra_even": "#22252c",
    "zebra_odd": "#1b1e24"
}

class FlatButton(tk.Label):
    """
    Plattformunabhängiger Button mit 100% Farbgarantie auf macOS.
    Verhindert, dass macOS Aqua den Hintergrund mit Weiß überschreibt.
    """
    def __init__(self, parent, text, command=None, bg_color=None, hover_color=None,
                 fg_color="#ffffff", font=("SF Pro Text", 11, "bold"), padx=14, pady=8,
                 border_color=None, **kwargs):
        self.bg_color = bg_color or THEME["btn_bg"]
        self.hover_color = hover_color or THEME["btn_hover"]
        self.fg_color = fg_color
        self.border_color = border_color or THEME["card_border"]
        self.command = command
        self._disabled = False

        super().__init__(
            parent, text=text, bg=self.bg_color, fg=self.fg_color,
            font=font, padx=padx, pady=pady, cursor="pointinghand",
            highlightbackground=self.border_color, highlightthickness=1 if self.border_color else 0,
            **kwargs
        )

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_click(self, event):
        if not self._disabled and self.command:
            self.command()

    def _on_enter(self, event):
        if not self._disabled:
            self.config(bg=self.hover_color)

    def _on_leave(self, event):
        if not self._disabled:
            self.config(bg=self.bg_color)

    def set_state(self, state="normal", text=None, bg=None):
        if state == "disabled":
            self._disabled = True
            self.config(bg="#353b48", fg="#7f8c8d", cursor="arrow")
            if text:
                self.config(text=text)
        else:
            self._disabled = False
            self.config(bg=bg or self.bg_color, fg=self.fg_color, cursor="pointinghand")
            if text:
                self.config(text=text)


class FritzIPChangerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Fritz!Box IP-Manager {APP_VERSION}")
        self.geometry("820x720")
        self.minsize(760, 640)
        self.configure(bg=THEME["window_bg"])

        self.current_ip = "Wird ermittelt..."
        self.is_reconnecting = False
        self.fritz_client = FritzBoxClient()

        self._setup_styles()
        self._build_ui()
        self._load_history_to_table()

        # Initiale Abfragen im Hintergrund
        threading.Thread(target=self._initial_check, daemon=True).start()

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Treeview",
                        font=("SF Pro Text", 11),
                        rowheight=30,
                        background=THEME["card_bg"],
                        fieldbackground=THEME["card_bg"],
                        foreground=THEME["text_primary"],
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        font=("SF Pro Text", 11, "bold"),
                        padding=8,
                        background="#2c3240",
                        foreground="#ffffff",
                        borderwidth=0)
        style.map("Treeview",
                  background=[("selected", THEME["accent"])],
                  foreground=[("selected", "#ffffff")])

    def _build_ui(self):
        main_frame = tk.Frame(self, bg=THEME["window_bg"], padx=24, pady=18)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ==========================================
        # 1. HEADER (Symmetrisch mit Version Badge & Actions)
        # ==========================================
        header_frame = tk.Frame(main_frame, bg=THEME["window_bg"])
        header_frame.pack(fill=tk.X, pady=(0, 16))

        # Links: Titel + Badge
        header_left = tk.Frame(header_frame, bg=THEME["window_bg"])
        header_left.pack(side=tk.LEFT)

        lbl_title = tk.Label(header_left, text="🌐 Fritz!Box IP-Manager", font=("SF Pro Display", 20, "bold"),
                             bg=THEME["window_bg"], fg=THEME["text_primary"])
        lbl_title.pack(side=tk.LEFT, anchor="center")

        lbl_badge = tk.Label(header_left, text=f" {APP_VERSION} ", font=("SF Pro Text", 10, "bold"),
                             bg=THEME["accent"], fg="#ffffff", padx=6, pady=2)
        lbl_badge.pack(side=tk.LEFT, padx=(10, 0))

        # Rechts: Einstellungs-Button
        btn_settings = FlatButton(header_frame, text="⚙️ Einstellungen / Router",
                                  command=self._open_settings,
                                  bg_color=THEME["card_bg"], hover_color=THEME["btn_hover"],
                                  border_color=THEME["card_border"], padx=14, pady=6)
        btn_settings.pack(side=tk.RIGHT)

        # ==========================================
        # 2. SYMMETRISCHE 2-SPALTEN KARTEN (IP & Router-Status)
        # ==========================================
        hero_grid = tk.Frame(main_frame, bg=THEME["window_bg"])
        hero_grid.pack(fill=tk.X, pady=(0, 16))
        hero_grid.columnconfigure(0, weight=1, uniform="hero")
        hero_grid.columnconfigure(1, weight=1, uniform="hero")

        # --- Linke Karte: Aktuelle IP ---
        card_ip = tk.Frame(hero_grid, bg=THEME["card_bg"], highlightbackground=THEME["card_border"],
                           highlightthickness=1, padx=16, pady=14)
        card_ip.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        ip_top = tk.Frame(card_ip, bg=THEME["card_bg"])
        ip_top.pack(fill=tk.X)
        tk.Label(ip_top, text="AKTUELLE ÖFFENTLICHE IP", font=("SF Pro Text", 9, "bold"),
                 bg=THEME["card_bg"], fg=THEME["text_secondary"]).pack(side=tk.LEFT)
        self.lbl_ip_badge = tk.Label(ip_top, text="● Verbunden", font=("SF Pro Text", 10, "bold"),
                                     bg=THEME["card_bg"], fg=THEME["success"])
        self.lbl_ip_badge.pack(side=tk.RIGHT)

        self.lbl_ip = tk.Label(card_ip, text="...", font=("SF Mono", 22, "bold"),
                               bg=THEME["window_bg"], fg=THEME["text_primary"],
                               pady=8, relief="solid", bd=1)
        self.lbl_ip.pack(fill=tk.X, pady=(10, 10))

        ip_actions = tk.Frame(card_ip, bg=THEME["card_bg"])
        ip_actions.pack(fill=tk.X)
        ip_actions.columnconfigure(0, weight=1)
        ip_actions.columnconfigure(1, weight=1)

        btn_copy = FlatButton(ip_actions, text="📋 Kopieren", command=self._copy_ip,
                              bg_color=THEME["btn_bg"], hover_color=THEME["btn_hover"],
                              border_color=THEME["input_border"], pady=7)
        btn_copy.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        btn_refresh = FlatButton(ip_actions, text="🔄 Prüfen", command=self._check_ip_clicked,
                                bg_color=THEME["btn_bg"], hover_color=THEME["btn_hover"],
                                border_color=THEME["input_border"], pady=7)
        btn_refresh.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # --- Rechte Karte: Router Status ---
        card_router = tk.Frame(hero_grid, bg=THEME["card_bg"], highlightbackground=THEME["card_border"],
                               highlightthickness=1, padx=16, pady=14)
        card_router.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        router_top = tk.Frame(card_router, bg=THEME["card_bg"])
        router_top.pack(fill=tk.X)
        tk.Label(router_top, text="FRITZ!BOX STATUS", font=("SF Pro Text", 9, "bold"),
                 bg=THEME["card_bg"], fg=THEME["text_secondary"]).pack(side=tk.LEFT)
        self.lbl_router_badge = tk.Label(router_top, text="● Prüfe...", font=("SF Pro Text", 10, "bold"),
                                         bg=THEME["card_bg"], fg=THEME["warning"])
        self.lbl_router_badge.pack(side=tk.RIGHT)

        router_info_box = tk.Frame(card_router, bg=THEME["window_bg"], pady=8, padx=12, relief="solid", bd=1)
        router_info_box.pack(fill=tk.X, pady=(10, 10))

        self.lbl_router_host = tk.Label(router_info_box, text="Host: 192.168.178.1", font=("SF Pro Text", 12, "bold"),
                                        bg=THEME["window_bg"], fg=THEME["text_primary"])
        self.lbl_router_host.pack(anchor="w")

        self.lbl_router_mode = tk.Label(router_info_box, text="Modus: TR-064 & UPnP aktiv", font=("SF Pro Text", 10),
                                        bg=THEME["window_bg"], fg=THEME["text_secondary"])
        self.lbl_router_mode.pack(anchor="w", pady=(2, 0))

        router_actions = tk.Frame(card_router, bg=THEME["card_bg"])
        router_actions.pack(fill=tk.X)
        router_actions.columnconfigure(0, weight=1)

        btn_open_settings = FlatButton(router_actions, text="🔧 Konfigurieren", command=self._open_settings,
                                       bg_color=THEME["btn_bg"], hover_color=THEME["btn_hover"],
                                       border_color=THEME["input_border"], pady=7)
        btn_open_settings.grid(row=0, column=0, sticky="ew")

        # ==========================================
        # 3. RECONNECT ACTION HERO (Mitte)
        # ==========================================
        card_action = tk.Frame(main_frame, bg=THEME["card_bg"], highlightbackground=THEME["card_border"],
                               highlightthickness=1, padx=20, pady=18)
        card_action.pack(fill=tk.X, pady=(0, 16))

        self.btn_reconnect = FlatButton(card_action, text="⚡ Neue IP anfordern (1-Klick Reconnect)",
                                        command=self._start_reconnect,
                                        bg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                                        fg_color="#ffffff", font=("SF Pro Display", 15, "bold"),
                                        border_color="#0070c9", pady=14)
        self.btn_reconnect.pack(fill=tk.X)

        self.progress = ttk.Progressbar(card_action, mode="indeterminate")

        self.lbl_action_status = tk.Label(card_action, text="Bereit für IP-Erneuerung über die Fritz!Box.",
                                          font=("SF Pro Text", 11), bg=THEME["card_bg"], fg=THEME["text_secondary"])
        self.lbl_action_status.pack(anchor="center", pady=(10, 0))

        # ==========================================
        # 4. IP-TRACKING HISTORIE TABELLE
        # ==========================================
        hist_bar = tk.Frame(main_frame, bg=THEME["window_bg"])
        hist_bar.pack(fill=tk.X, pady=(0, 8))

        hist_title_box = tk.Frame(hist_bar, bg=THEME["window_bg"])
        hist_title_box.pack(side=tk.LEFT)

        tk.Label(hist_title_box, text="📊 IP-Tracking Verlauf", font=("SF Pro Display", 14, "bold"),
                 bg=THEME["window_bg"], fg=THEME["text_primary"]).pack(side=tk.LEFT)

        self.lbl_hist_count = tk.Label(hist_title_box, text="(0 Einträge)", font=("SF Pro Text", 10),
                                       bg=THEME["window_bg"], fg=THEME["text_secondary"])
        self.lbl_hist_count.pack(side=tk.LEFT, padx=(8, 0))

        btn_clear = FlatButton(hist_bar, text="Verlauf leeren", command=self._clear_history,
                               bg_color=THEME["window_bg"], hover_color=THEME["card_bg"],
                               fg_color=THEME["danger"], font=("SF Pro Text", 10),
                               border_color=None, padx=10, pady=4)
        btn_clear.pack(side=tk.RIGHT)

        btn_export = FlatButton(hist_bar, text="📥 Als CSV exportieren", command=self._export_csv,
                                bg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                                fg_color="#ffffff", font=("SF Pro Text", 10, "bold"),
                                border_color=None, padx=12, pady=5)
        btn_export.pack(side=tk.RIGHT, padx=10)

        table_card = tk.Frame(main_frame, bg=THEME["card_bg"], highlightbackground=THEME["card_border"],
                              highlightthickness=1)
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("timestamp", "old_ip", "new_ip", "changed", "duration", "status")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("timestamp", text="Zeitpunkt")
        self.tree.heading("old_ip", text="Vorherige IP")
        self.tree.heading("new_ip", text="Neue IP")
        self.tree.heading("changed", text="Gewechselt?")
        self.tree.heading("duration", text="Dauer")
        self.tree.heading("status", text="Status")

        self.tree.column("timestamp", width=150, anchor="w")
        self.tree.column("old_ip", width=140, anchor="center")
        self.tree.column("new_ip", width=140, anchor="center")
        self.tree.column("changed", width=90, anchor="center")
        self.tree.column("duration", width=75, anchor="center")
        self.tree.column("status", width=160, anchor="w")

        self.tree.tag_configure("even", background=THEME["zebra_even"])
        self.tree.tag_configure("odd", background=THEME["zebra_odd"])

        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ==========================================
    # LOGIK & HINTERGRUND-WORKER
    # ==========================================
    def _initial_check(self):
        self.fritz_client = FritzBoxClient()

        reachable = self.fritz_client.is_reachable()
        if reachable:
            self.lbl_router_badge.config(text="● Verbunden", fg=THEME["success"])
            self.lbl_router_host.config(text=f"Host: {self.fritz_client.host}")
            mode_text = "Modus: TR-064 Login aktiv" if self.fritz_client.password else "Modus: UPnP IGD"
            self.lbl_router_mode.config(text=mode_text)
        else:
            self.lbl_router_badge.config(text="● Getrennt", fg=THEME["danger"])
            self.lbl_router_host.config(text=f"Host: {self.fritz_client.host} (Nicht erreichbar)")

        ip = self.fritz_client.get_fritzbox_external_ip()
        if not ip:
            ip = IPTracker.get_public_ip()
        
        self.current_ip = ip or "Nicht verfügbar"
        self.after(0, lambda: self._update_ip_display(self.current_ip))

    def _update_ip_display(self, ip):
        self.current_ip = ip
        self.lbl_ip.config(text=ip if ip else "Unbekannt")
        if ip and ip not in ["...", "Wird ermittelt...", "Nicht verfügbar"]:
            self.lbl_ip_badge.config(text="● Verbunden", fg=THEME["success"])
        else:
            self.lbl_ip_badge.config(text="● Getrennt", fg=THEME["danger"])

    def _copy_ip(self):
        if self.current_ip and self.current_ip not in ["...", "Wird ermittelt...", "Nicht verfügbar"]:
            self.clipboard_clear()
            self.clipboard_append(self.current_ip)
            self.lbl_action_status.config(text=f"IP {self.current_ip} in die Zwischenablage kopiert! 📋", fg=THEME["success"])
        else:
            messagebox.showinfo("Kopieren", "Keine gültige IP-Adresse vorhanden.")

    def _check_ip_clicked(self):
        self.lbl_ip_badge.config(text="● Prüfe...", fg=THEME["warning"])
        self.lbl_ip.config(text="Wird ermittelt...")
        def worker():
            ip = self.fritz_client.get_fritzbox_external_ip()
            if not ip:
                ip = IPTracker.get_public_ip()
            self.after(0, lambda: self._update_ip_display(ip))
            self.after(0, lambda: self.lbl_action_status.config(text=f"IP-Prüfung abgeschlossen: {ip}", fg=THEME["text_secondary"]))
        threading.Thread(target=worker, daemon=True).start()

    def _start_reconnect(self):
        if self.is_reconnecting:
            return
        self.is_reconnecting = True
        self.btn_reconnect.set_state("disabled", text="⏳ Reconnect läuft...")
        self.progress.pack(fill=tk.X, pady=(12, 0))
        self.progress.start(10)
        self.lbl_ip_badge.config(text="● Trennung...", fg=THEME["warning"])

        threading.Thread(target=self._reconnect_worker, daemon=True).start()

    def _reconnect_worker(self):
        start_time = time.time()
        old_ip = self.current_ip if self.current_ip not in ["...", "Wird ermittelt...", "Nicht verfügbar"] else None

        self._set_status("Schritt 1/3: Sende Trennungsbefehl an Fritz!Box...")
        success, msg = self.fritz_client.reconnect()

        if not success:
            duration = time.time() - start_time
            self.after(0, lambda: self._finish_reconnect(False, old_ip, old_ip, duration, msg))
            return

        self._set_status("Schritt 2/3: Verbindung getrennt. Warte auf Neuverbindung...")
        time.sleep(4)

        new_ip = None
        max_wait = 45
        check_interval = 2.0
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(check_interval)
            elapsed = time.time() - start_time
            self._set_status(f"Schritt 3/3: Warte auf neue IP ({elapsed:.0f}s)...")

            detected_ip = self.fritz_client.get_fritzbox_external_ip()
            if not detected_ip:
                detected_ip = IPTracker.get_public_ip(timeout=3)
            
            if detected_ip and detected_ip != "0.0.0.0" and (detected_ip != old_ip or elapsed > 15):
                new_ip = detected_ip
                break

        duration = time.time() - start_time

        if new_ip:
            if old_ip and new_ip != old_ip:
                status_text = f"Erfolgreich gewechselt! ({new_ip})"
            elif old_ip and new_ip == old_ip:
                status_text = f"Gleiche IP zugewiesen ({new_ip})"
            else:
                status_text = f"Neue IP erhalten: {new_ip}"
            self.after(0, lambda: self._finish_reconnect(True, old_ip, new_ip, duration, status_text))
        else:
            self.after(0, lambda: self._finish_reconnect(False, old_ip, None, duration, "Timeout beim Warten auf neue IP"))

    def _set_status(self, text):
        self.after(0, lambda: self.lbl_action_status.config(text=text, fg=THEME["text_secondary"]))

    def _finish_reconnect(self, success, old_ip, new_ip, duration, status_msg):
        self.is_reconnecting = False
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_reconnect.set_state("normal", text="⚡ Neue IP anfordern (1-Klick Reconnect)", bg=THEME["accent"])

        if success and new_ip:
            self._update_ip_display(new_ip)
            is_changed = (old_ip != new_ip) if (old_ip and new_ip) else False
            entry = IPTracker.add_history_entry(old_ip, new_ip, duration, "Erfolgreich" if is_changed else "IP unverändert")
            self._insert_table_row(entry)
            self._update_history_count()
            self.lbl_action_status.config(text=f"✅ Fertig in {duration:.1f}s: {status_msg}", fg=THEME["success"])
            notify_macos("Fritz!Box IP gewechselt", f"Neue IP: {new_ip} (in {duration:.1f}s)")
        else:
            entry = IPTracker.add_history_entry(old_ip, new_ip or "-", duration, status_msg[:50])
            self._insert_table_row(entry)
            self._update_history_count()
            self.lbl_action_status.config(text="⚠️ Reconnect konnte nicht ausgeführt werden.", fg=THEME["danger"])
            messagebox.showwarning("Reconnect Hinweis", status_msg)

    def _load_history_to_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        history = IPTracker.load_history()
        for i, entry in enumerate(history):
            self._insert_table_row(entry, append_bottom=True, row_index=i)
        self._update_history_count()

    def _update_history_count(self):
        cnt = len(self.tree.get_children())
        self.lbl_hist_count.config(text=f"({cnt} {'Eintrag' if cnt == 1 else 'Einträge'})")

    def _insert_table_row(self, entry, append_bottom=False, row_index=None):
        changed_str = "✅ Ja" if entry.get("changed") else ("ℹ️ Nein" if entry.get("old_ip") != "-" else "-")
        values = (
            entry.get("timestamp", ""),
            entry.get("old_ip", ""),
            entry.get("new_ip", ""),
            changed_str,
            entry.get("duration", ""),
            entry.get("status", "")
        )
        tag = "even" if (row_index or len(self.tree.get_children())) % 2 == 0 else "odd"
        if append_bottom:
            self.tree.insert("", "end", values=values, tags=(tag,))
        else:
            self.tree.insert("", 0, values=values, tags=(tag,))

    def _clear_history(self):
        if messagebox.askyesno("Verlauf leeren", "Möchtest du den gesamten IP-Tracking Verlauf löschen?"):
            IPTracker.clear_history()
            self._load_history_to_table()
            self.lbl_action_status.config(text="IP-Verlauf gelöscht.", fg=THEME["text_secondary"])

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            initialfile=f"fritzbox_ip_history_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if path:
            if IPTracker.export_csv(path):
                messagebox.showinfo("Export erfolgreich", f"Historie gespeichert unter:\n{path}")
            else:
                messagebox.showerror("Export fehlgeschlagen", "Fehler beim Exportieren der Datei.")

    def _open_settings(self):
        SettingsDialog(self)


# ==========================================
# EINSTELLUNGS-DIALOG (Symmetrisch & Modern)
# ==========================================
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Fritz!Box Konfiguration")
        self.geometry("540x560")
        self.minsize(500, 520)
        self.configure(bg=THEME["window_bg"])
        self.transient(parent)

        self.cfg = load_config()

        pad = {"padx": 20, "pady": 4}
        
        # Header
        tk.Label(self, text="Fritz!Box Einstellungen", font=("SF Pro Display", 16, "bold"),
                 bg=THEME["window_bg"], fg=THEME["text_primary"]).pack(pady=(18, 12))

        form_card = tk.Frame(self, bg=THEME["card_bg"], highlightbackground=THEME["card_border"],
                             highlightthickness=1, padx=16, pady=16)
        form_card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))

        # Router IP
        tk.Label(form_card, text="Router IP / Adresse:", font=("SF Pro Text", 10, "bold"),
                 bg=THEME["card_bg"], fg=THEME["text_primary"], anchor="w").pack(fill=tk.X, **pad)
        
        host_row = tk.Frame(form_card, bg=THEME["card_bg"])
        host_row.pack(fill=tk.X, padx=20, pady=(0, 8))
        
        self.ent_host = tk.Entry(host_row, bg=THEME["input_bg"], fg=THEME["input_fg"],
                                 insertbackground=THEME["input_fg"], relief="solid", bd=1,
                                 font=("SF Mono", 12))
        self.ent_host.insert(0, self.cfg.get("host", "192.168.178.1"))
        self.ent_host.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        btn_auto_ip = FlatButton(host_row, text="Auto-Erkennen", command=self._auto_detect_ip,
                                 bg_color=THEME["input_bg"], hover_color=THEME["btn_hover"],
                                 border_color=THEME["input_border"], padx=10, pady=4,
                                 font=("SF Pro Text", 10, "bold"))
        btn_auto_ip.pack(side=tk.RIGHT, padx=(8, 0))

        # Separator
        tk.Frame(form_card, height=1, bg=THEME["card_border"]).pack(fill=tk.X, padx=10, pady=12)

        # Login Sektion
        tk.Label(form_card, text="Fritz!Box Authentifizierung (Optional):", font=("SF Pro Text", 11, "bold"),
                 bg=THEME["card_bg"], fg=THEME["text_primary"], anchor="w").pack(fill=tk.X, padx=20)
        tk.Label(form_card, text="Wird für TR-064 Reconnect genutzt, falls UPnP geschützt ist.",
                 font=("SF Pro Text", 9), bg=THEME["card_bg"], fg=THEME["text_secondary"], anchor="w").pack(fill=tk.X, padx=20, pady=(0, 8))

        # Benutzername
        tk.Label(form_card, text="Benutzername:", font=("SF Pro Text", 10),
                 bg=THEME["card_bg"], fg=THEME["text_primary"], anchor="w").pack(fill=tk.X, padx=20, pady=(4, 2))
        self.ent_user = tk.Entry(form_card, bg=THEME["input_bg"], fg=THEME["input_fg"],
                                 insertbackground=THEME["input_fg"], relief="solid", bd=1,
                                 font=("SF Pro Text", 11))
        detected_user = self.cfg.get("username") or self.master.fritz_client.get_detected_username() or ""
        self.ent_user.insert(0, detected_user)
        self.ent_user.pack(fill=tk.X, padx=20, pady=(0, 8), ipady=4)

        # Kennwort
        tk.Label(form_card, text="Kennwort:", font=("SF Pro Text", 10),
                 bg=THEME["card_bg"], fg=THEME["text_primary"], anchor="w").pack(fill=tk.X, padx=20, pady=(4, 2))
        
        pass_row = tk.Frame(form_card, bg=THEME["card_bg"])
        pass_row.pack(fill=tk.X, padx=20, pady=(0, 8))
        self.ent_pass = tk.Entry(pass_row, bg=THEME["input_bg"], fg=THEME["input_fg"],
                                 insertbackground=THEME["input_fg"], relief="solid", bd=1,
                                 show="*", font=("SF Pro Text", 11))
        self.ent_pass.insert(0, self.cfg.get("password", ""))
        self.ent_pass.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        self.btn_show_pw = FlatButton(pass_row, text="👁️", command=self._toggle_show_pw,
                                      bg_color=THEME["input_bg"], hover_color=THEME["btn_hover"],
                                      border_color=THEME["input_border"], padx=8, pady=4)
        self.btn_show_pw.pack(side=tk.RIGHT, padx=(6, 0))

        # Status Label für Testergebnis
        self.lbl_test_result = tk.Label(form_card, text="", font=("SF Pro Text", 11, "bold"),
                                        bg=THEME["card_bg"], fg=THEME["text_primary"], wraplength=460, justify="left")
        self.lbl_test_result.pack(fill=tk.X, padx=20, pady=(6, 8))

        # Test Button
        self.btn_test = FlatButton(form_card, text="🔑 Anmelden & Verbindung testen",
                                  command=self._test_login,
                                  bg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                                  fg_color="#ffffff", font=("SF Pro Text", 12, "bold"),
                                  border_color="#0070c9", pady=10)
        self.btn_test.pack(fill=tk.X, padx=20, pady=(4, 6))

        # Bottom buttons
        btn_frame = tk.Frame(self, bg=THEME["window_bg"])
        btn_frame.pack(fill=tk.X, pady=(0, 16), padx=20)

        btn_save = FlatButton(btn_frame, text="Speichern & Schließen", command=self._save,
                              bg_color=THEME["success"], hover_color="#55efc4",
                              fg_color="#ffffff", font=("SF Pro Text", 11, "bold"),
                              border_color="#008f6b", padx=16, pady=8)
        btn_save.pack(side=tk.RIGHT)

        btn_cancel = FlatButton(btn_frame, text="Abbrechen", command=self.destroy,
                                bg_color=THEME["card_bg"], hover_color=THEME["btn_hover"],
                                fg_color=THEME["text_secondary"], font=("SF Pro Text", 11),
                                border_color=THEME["card_border"], padx=14, pady=8)
        btn_cancel.pack(side=tk.RIGHT, padx=10)

    def _toggle_show_pw(self):
        if self.ent_pass.cget("show") == "":
            self.ent_pass.config(show="*")
        else:
            self.ent_pass.config(show="")

    def _auto_detect_ip(self):
        gw = detect_fritzbox_host()
        self.ent_host.delete(0, tk.END)
        self.ent_host.insert(0, gw)
        self.lbl_test_result.config(text=f"Fritz!Box erkannt unter: {gw}", fg=THEME["accent_hover"])

    def _test_login(self):
        host = self.ent_host.get().strip() or "192.168.178.1"
        user = self.ent_user.get().strip()
        pwd = self.ent_pass.get()

        self.lbl_test_result.config(text="⏳ Prüfe Verbindung und Anmeldung...", fg=THEME["accent_hover"])
        self.btn_test.set_state("disabled", text="⏳ Teste Verbindung...")
        self.update_idletasks()

        def worker():
            try:
                client = FritzBoxClient(host=host, username=user, password=pwd)

                if not client.is_reachable():
                    self.after(0, lambda: self._show_test_result(False, f"❌ Router unter {host} nicht erreichbar. Prüfe WLAN/LAN."))
                    return

                if pwd:
                    ok, sid, msg = client.login_with_sid(username=user, password=pwd)
                    if ok:
                        self.cfg["host"] = host
                        self.cfg["username"] = user
                        self.cfg["password"] = pwd
                        save_config(self.cfg)
                        self.master.fritz_client = FritzBoxClient()
                        self.master._initial_check()
                        self.after(0, lambda: self._show_test_result(True, f"✅ Erfolgreich angemeldet als '{user}'! (Gespeichert)"))
                    else:
                        self.after(0, lambda: self._show_test_result(False, f"❌ {msg}"))
                else:
                    ext_ip = client.get_fritzbox_external_ip()
                    if ext_ip:
                        self.after(0, lambda: self._show_test_result(True, f"✅ Fritz!Box erreichbar! Externe IP: {ext_ip}"))
                    else:
                        self.after(0, lambda: self._show_test_result(False, "⚠️ Router erreichbar, aber kein Kennwort eingegeben."))
            except Exception as e:
                self.after(0, lambda: self._show_test_result(False, f"❌ Fehler beim Testen: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_test_result(self, success, text):
        self.btn_test.set_state("normal", text="🔑 Anmelden & Verbindung testen")
        self.lbl_test_result.config(text=text, fg=THEME["success"] if success else THEME["danger"])

    def _save(self):
        self.cfg["host"] = self.ent_host.get().strip() or "192.168.178.1"
        self.cfg["username"] = self.ent_user.get().strip()
        self.cfg["password"] = self.ent_pass.get()

        save_config(self.cfg)
        self.master.fritz_client = FritzBoxClient()
        self.master._initial_check()
        self.destroy()

if __name__ == "__main__":
    app = FritzIPChangerApp()
    app.mainloop()
