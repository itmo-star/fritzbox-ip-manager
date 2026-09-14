# 🌐 Fritz!Box IP-Manager & Tracker `v1.01`

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-lightgrey.svg)](https://apple.com)
[![Fritz!OS: 7.x%20%2F%208.x](https://img.shields.io/badge/Fritz!OS-7.x%20%2F%208.x-orange.svg)](https://avm.de)

Ein leichtgewichtiges, symmetrisches macOS-Desktoptool zur **1-Klick-Erneuerung der öffentlichen IP-Adresse** über eine AVM Fritz!Box (DSL, Glasfaser/FTTH, Kabel) inklusive lückenlosem **IP-Tracking-Verlauf** und CSV-Export.

---

## ✨ Features

- **⚡ 1-Klick Reconnect:** Trennt die externe WAN-Verbindung und fordert sofort eine neue dynamische öffentliche IP-Adresse vom Internet-Provider an.
- **🏠 Gilt für das gesamte Heimnetz:** Alle Geräte im Haushalt (Laptops, Smartphones, Smart-TVs) surfen sofort mit der neuen IP.
- **📊 Lückenlose IP-Historie:** Protokolliert automatisch jeden Wechsel (Zeitpunkt, vorherige IP, neue IP, Wechsel-Status, Reconnect-Dauer in Sekunden).
- **📥 CSV-Export:** Exportiere den IP-Verlauf mit einem Klick für eigene Tracking- und Sicherheitsanalysen.
- **🔒 Volle Privatsphäre:** Lokale Ausführung, keine Cloud, keine externen Tracker. Lokale Zugangsdaten und IP-Historie sind standardmäßig per `.gitignore` geschützt und werden nie ins Git-Repository übertragen.
- **🎨 Modernes macOS Dark-Design:** Symmetrisches 2-Spalten-Layout, Zebra-Striping in der Tabelle, native macOS-Benachrichtigungen.
- **🚀 Zero Dependencies:** Basiert ausschließlich auf der Python 3 Standardbibliothek (kein `pip install` nötig).

---

## 🛠️ Schnellstart

### 1. Repository klonen
```bash
git clone https://github.com/DEIN-USERNAME/fritzbox-ip-manager.git
cd fritzbox-ip-manager
```

### 2. Anwendung starten
Einfach mit Python 3 starten:
```bash
python3 app.py
```
*(Oder per Doppelklick auf `Start_FritzBox_IP_Changer.command`)*

---

## ⚙️ Fritz!Box Konfiguration (2 Wege)

Die Anwendung unterstützt sowohl den passwortlosen UPnP-Modus als auch die TR-064-Authentifizierung:

### Weg A: 1-Klick ohne Passwort (Empfohlen)
1. Im Browser die Fritz!Box öffnen (`http://192.168.178.1`).
2. Menü: **Heimnetz** ➔ **Netzwerk** ➔ Reiter **Netzwerkeinstellungen**.
3. Unter **Heimnetzfreigaben** folgende Haken setzen:
   - [x] **Statusinformationen über UPnP übertragen**
   - [x] **Änderungen der Sicherheitseinstellungen über UPnP gestatten**
4. Auf **Übernehmen** klicken.

### Weg B: Mit Zugangsdaten (TR-064)
Falls UPnP ohne Authentifizierung nicht freigegeben werden soll:
1. In der App oben rechts auf **⚙️ Einstellungen** klicken.
2. Fritz!Box Benutzername und Kennwort eingeben.
3. Auf **"🔑 Anmelden & Verbindung testen"** klicken — die Zugangsdaten werden sicher lokal in der `config.json` gespeichert (wird von Git ignoriert).

---

## 🔒 Privatsphäre & Open-Source Sicherheit

Dieses Repository ist so konfiguriert, dass **keine persönlichen Daten** ins Versionskontrollsystem gelangen:
- Die Datei `config.json` (mit deinem Kennwort/Benutzer) ist in der `.gitignore` eingetragen.
- Die Datei `ip_history.json` (mit deinen bezogenen öffentlichen IPs) ist in der `.gitignore` eingetragen.
- Eine neutrale Konfigurationsvorlage liegt als `config.example.json` bereit.

---

## 📄 Lizenz

Dieses Projekt ist unter der [MIT-Lizenz](LICENSE) lizenziert.
