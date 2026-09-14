"""
Fritz!Box IP Reconnect & Tracking Service
Unterstützt:
1. TR-064 mit Authentifizierung (Benutzername & Passwort)
2. UPnP IGD ForceTermination (1-Klick ohne Passwort, wenn in Fritz!Box freigegeben)
3. Automatische Erkennung der Fritz!Box IP (192.168.178.1 / Standard-Gateway)
"""

import os
import json
import csv
import time
import socket
import subprocess
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
import xml.etree.ElementTree as ET

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ip_history.json")

def detect_fritzbox_host():
    """Ermittelt zuverlässig die IP-Adresse der lokalen Fritz!Box."""
    # 1. Standard AVM IP testen
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        if sock.connect_ex(("192.168.178.1", 80)) == 0 or sock.connect_ex(("192.168.178.1", 49000)) == 0:
            sock.close()
            return "192.168.178.1"
        sock.close()
    except Exception:
        pass

    # 2. Default Gateway via route ermitteln
    try:
        out = subprocess.check_output(["route", "-n", "get", "default"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "gateway:" in line:
                gw = line.split("gateway:")[1].strip()
                if gw and not gw.startswith("127."):
                    return gw
    except Exception:
        pass

    return "192.168.178.1"

DEFAULT_CONFIG = {
    "host": detect_fritzbox_host(),
    "port": 49000,
    "username": "",
    "password": "",
    "use_auth": False,
    "timeout": 8
}

PUBLIC_IP_SERVICES = [
    "https://api4.ipify.org",
    "https://icanhazip.com",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com"
]

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg.update(data)
                if cfg.get("host") == "fritz.box":
                    cfg["host"] = detect_fritzbox_host()
                return cfg
        except Exception:
            pass
    return cfg

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Fehler beim Speichern der Konfiguration: {e}")

class FritzBoxClient:
    def __init__(self, host=None, port=None, username=None, password=None, use_auth=None, timeout=8):
        cfg = load_config()
        self.host = host or cfg.get("host") or detect_fritzbox_host()
        self.port = port or cfg.get("port", 49000)
        self.username = username if username is not None else cfg.get("username", "")
        self.password = password if password is not None else cfg.get("password", "")
        self.use_auth = use_auth if use_auth is not None else cfg.get("use_auth", False)
        self.timeout = timeout or cfg.get("timeout", 8)

    def is_reachable(self):
        """Prüft, ob die Fritz!Box im lokalen Netz erreichbar ist."""
        for p in [self.port, 80]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.5)
                res = sock.connect_ex((self.host, int(p)))
                sock.close()
                if res == 0:
                    return True
            except Exception:
                continue
        return False

    def get_detected_username(self):
        """Liest den konfigurierten Benutzernamen dynamisch von der Fritz!Box aus."""
        try:
            url = f"http://{self.host}/login_sid.lua"
            with urllib.request.urlopen(url, timeout=3) as resp:
                root = ET.fromstring(resp.read())
                users = [u.text for u in root.iter("User") if u.text]
                if users:
                    return users[0]
        except Exception:
            pass
        return ""

    def login_with_sid(self, username=None, password=None):
        """
        Führt einen Fritz!OS Challenge-Response Login aus.
        Gibt (success: bool, sid: str, message: str) zurück.
        """
        user = username if username is not None else self.username
        pwd = password if password is not None else self.password

        url = f"http://{self.host}/login_sid.lua"
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                root = ET.fromstring(resp.read())
            
            sid = root.findtext("SID")
            if sid and sid != "0000000000000000":
                return True, sid, "Bereits mit gültiger Sitzung angemeldet"

            challenge = root.findtext("Challenge")
            if not challenge:
                return False, None, "Keine Challenge von Fritz!Box erhalten"

            challenge_and_pass = f"{challenge}-{pwd}"
            md5_hash = hashlib.md5(challenge_and_pass.encode("utf-16le")).hexdigest()
            response_str = f"{challenge}-{md5_hash}"

            post_data = urllib.parse.urlencode({
                "username": user,
                "response": response_str
            }).encode("utf-8")

            req = urllib.request.Request(url, data=post_data)
            with urllib.request.urlopen(req, timeout=12) as resp:
                root2 = ET.fromstring(resp.read())

            sid2 = root2.findtext("SID")
            if sid2 and sid2 != "0000000000000000":
                return True, sid2, f"Erfolgreich angemeldet als '{user}'"
            else:
                block_time = root2.findtext("BlockTime")
                msg = f"Kennwort für Benutzer '{user}' ist nicht korrekt."
                if block_time and int(block_time) > 0:
                    msg += f" (Fritz!Box Sperrzeit: {block_time}s)"
                return False, None, msg
        except Exception as e:
            return False, None, f"Verbindungsfehler zu {self.host}: {e}"

    def _soap_request(self, control_url, service_type, action, params=None, username=None, password=None):
        """Sendet einen UPnP oder TR-064 SOAP-Aufruf (optional mit Digest Auth)."""
        url = f"http://{self.host}:{self.port}{control_url}"
        
        body_params = ""
        if params:
            for k, v in params.items():
                body_params += f"<{k}>{v}</{k}>\n"

        soap_body = (
            f'<?xml version="1.0" encoding="utf-8"?>\n'
            f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\n'
            f'  <s:Body>\n'
            f'    <u:{action} xmlns:u="{service_type}">\n'
            f'      {body_params}'
            f'    </u:{action}>\n'
            f'  </s:Body>\n'
            f'</s:Envelope>'
        )

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SoapAction": f'"{service_type}#{action}"'
        }

        user = username if username is not None else self.username
        pwd = password if password is not None else self.password

        if user and pwd:
            passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(None, url, user, pwd)
            opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(passman))
        else:
            opener = urllib.request.build_opener()

        req = urllib.request.Request(url, data=soap_body.encode("utf-8"), headers=headers, method="POST")
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                return True, content, resp.status
        except urllib.error.HTTPError as e:
            content = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            return False, content, e.code
        except Exception as e:
            return False, str(e), 0

    def get_fritzbox_external_ip(self):
        """Fragt die externe IP via UPnP direkt von der Fritz!Box ab."""
        endpoints = [
            ("/igdupnp/control/WANIPConn1", "urn:schemas-upnp-org:service:WANIPConnection:1"),
            ("/igdupnp/control/WANPPPConn1", "urn:schemas-upnp-org:service:WANPPPConnection:1"),
            ("/upnp/control/wanipconnection1", "urn:dslforum-org:service:WANIPConnection:1"),
            ("/upnp/control/wanpppconn1", "urn:dslforum-org:service:WANPPPConnection:1"),
        ]

        for control_url, service_type in endpoints:
            success, response, _ = self._soap_request(control_url, service_type, "GetExternalIPAddress")
            if success:
                try:
                    root = ET.fromstring(response)
                    for elem in root.iter():
                        if "NewExternalIPAddress" in elem.tag and elem.text:
                            ip = elem.text.strip()
                            if ip and ip != "0.0.0.0":
                                return ip
                except Exception:
                    pass
        return None

    def reconnect(self):
        """
        Führt den Reconnect aus.
        1. TR-064 ForceTermination mit Authentifizierung (wenn Kennwort vorhanden)
        2. UPnP IGD ForceTermination (wenn UPnP ohne Passwort freigegeben ist)
        """
        # 1. TR-064 (mit Zugangsdaten)
        if self.password:
            tr064_endpoints = [
                ("/upnp/control/wanipconnection1", "urn:dslforum-org:service:WANIPConnection:1"),
                ("/upnp/control/wanpppconn1", "urn:dslforum-org:service:WANPPPConnection:1"),
            ]
            for control_url, service_type in tr064_endpoints:
                success, resp, code = self._soap_request(
                    control_url, service_type, "ForceTermination",
                    username=self.username, password=self.password
                )
                # 200 = OK, 707 = DisconnectInProgress (erfolgreich gestartet)
                if success or code == 200 or "707" in resp or "DisconnectInProgress" in resp:
                    return True, "TR-064 ForceTermination erfolgreich ausgelöst"

        # 2. UPnP IGD ForceTermination
        upnp_endpoints = [
            ("/igdupnp/control/WANIPConn1", "urn:schemas-upnp-org:service:WANIPConnection:1"),
            ("/igdupnp/control/WANPPPConn1", "urn:schemas-upnp-org:service:WANPPPConnection:1"),
        ]

        last_code = 0
        last_resp = ""
        for control_url, service_type in upnp_endpoints:
            success, resp, code = self._soap_request(control_url, service_type, "ForceTermination")
            if success or code == 200 or "707" in resp:
                return True, "UPnP ForceTermination erfolgreich gesendet"
            last_code = code
            last_resp = resp

        if last_code in (401, 500):
            return False, (
                "Fritz!Box Zugriff nicht erlaubt (UPnP 606 / Nicht autorisiert):\n\n"
                "👉 Lösung A (ohne Passwort):\n"
                "In der Fritz!Box unter Heimnetz -> Netzwerk -> Netzwerkeinstellungen\n"
                "den Haken bei 'Änderungen der Sicherheitseinstellungen über UPnP gestatten' setzen.\n\n"
                "👉 Lösung B (mit Kennwort):\n"
                "In der App oben auf '⚙️ Einstellungen' klicken und dein Fritz!Box-Kennwort eintragen."
            )
        
        return False, f"Verbindung konnte nicht getrennt werden (Code {last_code}). Bitte Verbindung zur Fritz!Box prüfen."


class IPTracker:
    @staticmethod
    def get_public_ip(timeout=4):
        """Ermittelt die aktuelle öffentliche IP-Adresse über externe Dienste."""
        for url in PUBLIC_IP_SERVICES:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "curl/7.88.1"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    ip = resp.read().decode("utf-8").strip()
                    if ip and ("." in ip or ":" in ip) and len(ip) < 50:
                        return ip
            except Exception:
                continue
        return None

    @staticmethod
    def load_history():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @staticmethod
    def add_history_entry(old_ip, new_ip, duration_sec, status="Erfolgreich"):
        history = IPTracker.load_history()
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "old_ip": old_ip or "-",
            "new_ip": new_ip or "-",
            "changed": (old_ip != new_ip) if (old_ip and new_ip) else False,
            "duration": f"{duration_sec:.1f}s",
            "status": status
        }
        history.insert(0, entry)
        if len(history) > 500:
            history = history[:500]
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Fehler beim Speichern der Historie: {e}")
        return entry

    @staticmethod
    def clear_history():
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
            return True
        except Exception:
            return False

    @staticmethod
    def export_csv(filepath):
        history = IPTracker.load_history()
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Zeitpunkt", "Alte IP", "Neue IP", "IP gewechselt?", "Dauer", "Status"])
                for item in history:
                    writer.writerow([
                        item.get("timestamp", ""),
                        item.get("old_ip", ""),
                        item.get("new_ip", ""),
                        "Ja" if item.get("changed") else "Nein",
                        item.get("duration", ""),
                        item.get("status", "")
                    ])
            return True
        except Exception as e:
            print(f"Fehler beim Exportieren: {e}")
            return False
