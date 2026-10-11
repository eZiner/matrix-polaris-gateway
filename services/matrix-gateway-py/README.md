# 🏛️ POLARIS: Matrix GeoFence & Form-Gateway (Python Alpha)

Dieses Verzeichnis enthält den leichtgewichtigen Python-Prototypen des **POLARIS-Gateways**. Der Bot dient als souveräne, föderierte Schnittstelle zwischen dem bürgernahen Kommunikationsprotokoll **Matrix** und einer **PostgreSQL/PostGIS** Geodatenbank. 

Er implementiert zwei deterministische, ressourcenschonende Kernkomponenten für die digitale Kommunalverwaltung (OZG-konform).

---

## 🚀 Kern-Features

### 1. Detachierter Live-GeoFence (PostGIS Spatial-Routing)
* **Protokoll-Integration:** Fängt native Matrix-Standort-Events (`m.location`) und Echtzeit-Live-Standorte (**Matrix-Beacons** via `org.matrix.msc3671.beacon`) im verschlüsselten Raum ab.
* **Hierarchisches Routing:** Gleicht GPS-Koordinaten (`Longitude, Latitude`) über eine räumliche `ST_Contains`-Indizierung live mit den echten Gemeindegrenzen (`main_zones`) und hyperlokalen Ortsteilen (`sub_zones`) ab.
* **Föderations-Weiche:** Liest den Amtlichen Regionalschlüssel (ARS) aus und berechnet die behördliche Zuständigkeit in Millisekunden auf souveräner Hardware.

### 2. Strukturierte Datenerfassung (Form-Drilldown-Dialoge)
* Bietet bürgerfreundliche, zustandsbasierte (stateful) Abfrage-Kaskaden im Chat.
* **Schadensmelder (`#schaden`):** Erfasst Infrastrukturmängel (Schlaglöcher, defekte Laternen, wilde Müllkippe) inklusive Adresse und Details.
* **Online-Hunderegister (`#hund`):** Automatisiert die steuerliche Anmeldung von Haustieren.
* **Daten-Archivierung:** Validiert die Eingaben und überführt sie in strukturierte, revisionssichere Datensätze.

---

## 🗄️ System-Architektur & Flussdiagramm

> [ BÜRGER: Element-Client ]
>            │
>            ▼ (Ende-zu-Ende-verschlüsselt über das Matrix-Protokoll)
> [ GATEWAY: rathaus_bot.py (matrix-nio) ]
>            │
>            ▼ (Lokale Docker-Bridge / localhost)
> [ GEODATENBANK: PostgreSQL / PostGIS Spatial Index ]

---

## 🛠️ Installation & Lokaler Betrieb

### 1. Voraussetzungen
Stelle sicher, dass im übergeordneten Verzeichnis eine gültige `.env`-Datei mit eurer `DATABASE_URL` (PostgreSQL) und den Matrix-Zugangsdaten existiert.

### 2. Umgebung aufsetzen
Wechsle in dieses Verzeichnis, erstelle die isolierte virtuelle Umgebung und installiere die bereinigten, minimalen Abhängigkeiten:

```bash
cd services/matrix-gateway-py/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Starten
Der Bot reaktiviert sich automatisch über bestehende Sitzungs-Token in der `bot_credentials.txt`, falls vorhanden:

```bash
python3 rathaus_bot.py
```

---

## 🔒 Sicherheit & Datenschutz (SecOps)
* **Zero-Data-Leakage:** Alle Daten verbleiben zu 100 % im Hoheitsgebiet des lokalen Servers. Keine Verbindung zu kommerziellen Drittanbieter-APIs.
* **Krypto-Sicherheit:** Sensible Sitzungsschlüssel (`bot_store/`) und Zugangsdaten (`bot_credentials.txt`) sind strikt über die `.gitignore` vom Git-Tracking ausgeschlossen.
