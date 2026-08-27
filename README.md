# 🌌 Matrix Polaris Gateway (matrix-polaris-gateway)

[Auf Deutsch lesen](#de-de-german) | [Read in English](#en-us-english)

---

## DE-DE (German)

Das **Matrix Polaris Gateway** ist ein datenschutzkonformes, hochgradig skalierbares Geo-Fencing-Gateway. Es ermöglicht die standortbasierte, automatisierte Steuerung von Matrix-Räumen für Kommunen, Behörden und den Tourismussektor im Rahmen eines bundesweiten, föderierten Bürgernetzes.

Developed by **eZiner** with 🐍 Python, `matrix-nio` and `shapely`.

### 💡 Das Konzept

Benannt nach dem Polarstern, der Seefahrern seit Jahrtausenden als fester, unverrückbarer Orientierungspunkt dient, bietet das **Matrix Polaris Gateway** dem Bürger einen verlässlichen Anker im digitalen Raum. Das System verbindet geografische Zonen (Polygone) direkt mit dem dezentralen Matrix-Netzwerk nach dem Prinzip **"Smart Server, Dumb Client"** – es ist *keine* Modifikation der Messenger-App des Nutzers und *kein* eigener App-Fork erforderlich.

#### Funktionsweise:
1. **Standort-Trigger:** Der Nutzer teilt seinen aktuellen Standort im privaten Bürger-Chat (entweder manuell oder via kontinuierlichem Live-Standort/Beacons im Auto oder auf dem Fahrrad) [Matrix Live Location Sharing Spec].
2. **Geo-Analyse:** Der Bot extrahiert die GPS-Koordinaten im Hintergrund und prüft über eine räumliche Abfrage, in welchem Geofence (z. B. Gemeindegrenze, touristische Zone) sich der Nutzer befindet.
3. **Automatischer Beitritt (Enter):** Befindet sich der Nutzer in einer Zone, sendet das Polaris-Gateway vollautomatisch eine Einladung (`room_invite`) in den regional zuständigen Info- oder Servicekanal.
4. **Automatischer Austritt (Exit):** Verlässt der Nutzer das geografische Polygon, wirft der Bot ihn via `room_kick` datenschutzkonform wieder aus dem temporären Raum aus. Das garantiert absolute Datenhygiene und verhindert "tote" Chat-Leichen in der App des Bürgers.

#### 🔒 Datenschutz & Sicherheit im Fokus

* **Kein permanentes Tracking:** Das System trackt den Nutzer nicht im Hintergrund. Eine Positionsbestimmung findet ausschließlich statt, wenn das Smartphone des Nutzers ein standardisiertes Matrix-Event (`m.location` oder `m.beacon`) absetzt [Matrix Live Location Sharing Spec].
* **Strikte Isolation:** Die Geodaten verbleiben im privaten 1-zu-1-Vorgangsraum zwischen Bürger und Bot. In den öffentlichen Informationskanälen wird der Standort *niemals* gepostet.
* **Ende-zu-Ende-Verschlüsselung (E2EE):** Der Bot unterstützt die sichere Megolm-Verschlüsselung. Die Geo-Daten fließen unlesbar über die Server-Infrastrukturen.

#### 🛠️ Installation & Setup (DE)

> [!CAUTION]
> **Experimenteller Prototyp – Nicht für den produktiven Einsatz geeignet!**
> 
> Der in diesem Repository bereitgestellte Quellcode (inklusive der `bot.py`) ist ein rein experimentelles Proof-of-Concept (PoC). Die aktuelle Architektur basiert auf Prototyping-Strukturen und erfüllt nicht die Performance-, Skalierungs- und Sicherheitsanforderungen für einen kritischen Produktivbetrieb.

##### Abhängigkeiten installieren
```bash
pip install matrix-nio shapely
```

##### Konfiguration
Öffnen Sie die `bot.py` und passen Sie die Verbindungsdaten sowie Ihr Geofence-Polygon an:
```python
MATRIX_HOMESERVER = "https://ihre-kommune.de"
BOT_USER_ID = "@polaris-bot:ihre-kommune.de"
BOT_PASSWORD = "IhrSicheresPasswort"
TOURIST_INFO_ROOM = "!raumid:matrix.org"
```

##### Starten
```bash
python bot.py
```

---

## EN-US (English)

The **Matrix Polaris Gateway** is a privacy-focused, highly scalable Geo-Fencing Gateway. It enables location-based, automated control of Matrix rooms designed for municipalities, public authorities, and the tourism sector within a nationwide federated citizen network.

Developed by **eZiner**.

### 💡 The Concept

Named after the North Star (Polaris), which has served navigators for millennia as a fixed, immovable point of orientation, the **Matrix Polaris Gateway** provides citizens with a reliable anchor in the digital space. The system maps geographic zones (polygons) directly to the decentralized, federated Matrix communication network. It follows a **"Smart Server, Dumb Client"** architecture – *no* modification of the user's messenger app and *no* custom app fork is required.

#### How it works:
1. **Location Trigger:** The user shares their current location inside a private chat (either manually or via continuous live location/beacons while driving or cycling) [Matrix Live Location Sharing Spec].
2. **Geo Analysis:** The bot extracts the GPS coordinates in the background and runs a spatial query to detect which geofence (e.g., municipal boundary, tourism zone) the user is currently in.
3. **Automated Join (Enter):** If the user enters a specific zone, the Matrix Polaris Gateway automatically sends an invitation (`room_invite`) to the regionally responsible info or service channel.
4. **Automated Leave (Exit):** Once the user leaves the geographic polygon, the bot kicks them out of the temporary room via `room_kick` in a privacy-compliant manner.

#### 🔒 Privacy & Security by Design

* **No Permanent Tracking:** The system does not silently track the user in the background. Location tracking only occurs when the user's smartphone explicitly broadcasts a standardized Matrix event (`m.location` or `m.beacon`) [Matrix Live Location Sharing Spec].
* **Strict Isolation:** All geographic data remains strictly inside the private 1-on-1 operations room between the citizen and the bot. Coordinates are *never* posted to public info channels.
* **End-to-End Encryption (E2EE):** The bot supports secure Megolm encryption. Location data is securely encrypted on the device and remains unreadable on the server database.

#### 🛠️ Installation & Setup (EN)

##### Install dependencies
```bash
pip install matrix-nio shapely
```

##### Configuration
Open `bot.py` and adjust the connection details and your custom geofence polygon:
```python
MATRIX_HOMESERVER = "https://your-municipality.com"
BOT_USER_ID = "@polaris-bot:your-municipality.com"
BOT_PASSWORD = "YourSecurePassword"
TOURIST_INFO_ROOM = "!roomid:matrix.org"
```

##### Run the Bot
```bash
python bot.py
```

---

## 🖥️ Production Deployment (Linux/systemd)

To run the bot as a background service in a secure environment:

1. Move the script to `/opt/polaris-bot/bot.py`.
2. Create the service file `/etc/systemd/system/polaris-bot.service`:

```ini
[Unit]
Description=Matrix Polaris Gateway - Geo-Fencing Service Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/polaris-bot
ExecStart=/usr/bin/python3 /opt/polaris-bot/bot.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable polaris-bot --now
```

---

## 📄 License & Trademark Disclaimer

This project is licensed under the **MIT License**. Feel free to use, modify, and integrate this software for any municipality or project without restrictions.

⚠️ **Rechtlicher Hinweis / Trademark Disclaimer:**  
*Matrix Polaris Gateway* ist ein von *eZiner* entwickeltes, rein unkommerzielles Open-Source-Infrastrukturprojekt zur Förderung der kommunalen und zivilgesellschaftlichen digitalen Souveränität. Der Name wird in seiner astronomischen Bedeutung (Polarstern) als freier Arbeitstitel verwendet. Es besteht keinerlei Verbindung zu bestehenden kommerziellen Marken, Unternehmen oder Softwareprodukten, die den Namen "Polaris" markenrechtlich nutzen. Alle filmischen oder literarischen Metaphern dienen ausschließlich der Veranschaulichung im Rahmen des wissenschaftlich-technischen Diskurses.
