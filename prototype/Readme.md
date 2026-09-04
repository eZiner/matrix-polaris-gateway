# 🐍 POLARIS Prototype Gateway (Python Layer)

Dieses Verzeichnis enthält den **asynchronen Python-Prototyp** des POLARIS Geo-Fencing Gateways. 

Der Prototyp ist darauf optimiert, neue Ideen, Schnittstellen und Logik-Workflows (wie das Zusammenspiel mit Infospaces) schnell und unkompliziert auszuprobieren. Er lauscht über `matrix-nio` in einer asynchronen Event-Schleife exklusiv im vordefinierten Bot-Raum, dechiffriert GPS-Koordinaten flüchtig im RAM und triggert den automatischen Beitritt (*Auto-Join*) via PostGIS-Abfrage.

---

## 🛠️ Technologie-Stack

* **Sprache:** Python 3.11+
* **Matrix-Protokoll:** `matrix-nio` (Asynchroner Matrix-Client mit E2EE-Support via libolm)
* **Datenbank-Treiber:** `asyncpg` (Hochperformanter, rein asynchroner PostgreSQL/PostGIS-Treiber)

---

## 💻 Lokale Entwicklung & Setup

Um den Prototyp lokal weiterzuentwickeln, wird die Nutzung einer virtuellen Umgebung (`.venv`) dringend empfohlen.

### 1. Abhängigkeiten installieren
Stelle sicher, dass du dich im Ordner `prototype/` befindest, erstelle das venv und installiere die Pakete:

```bash
# Virtuelle Umgebung erstellen
python -m venv .venv

# Aktivieren unter Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Alternativ unter Linux / macOS:
source .venv/bin/activate

# Pakete über den direkten Interpreter-Pfad installieren
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. VS Code Konfiguration
Wähle über `Strg + Umschalt + P` ➔ `Python: Select Interpreter` die soeben erstellte Umgebung (`.venv`) aus, damit der Code-Scanner (Pylance) alle Importe fehlerfrei versteht.

---

## 🐳 Docker-Entwicklungs-Setup (Live-Coding)

Um den Prototyp isoliert zu testen, ohne Python lokal auf deinem PC verwalten zu müssen, steht ein Entwicklungs-Dockerfile (`Dockerfile.dev`) bereit. Es ist so konfiguriert, dass es deinen lokalen Code per **Volume-Mount** spiegelt. Jede Änderung an deiner `bot.py` ist nach einem Container-Neustart sofort aktiv, ohne das Image neu bauen zu müssen.

### 1. Entwicklungs-Image bauen
```bash
docker build -f Dockerfile.dev -t polaris-prototype:dev .
```

### 2. Stack via Docker Compose starten
Am komfortabelsten startest du den Prototyp direkt im Verbund mit der PostGIS-Datenbank aus dem Hauptverzeichnis des Repositories:

```bash
# Zurück ins Hauptverzeichnis wechseln
cd ..

# Gesamten Prototyp-Stack im Hintergrund starten
docker compose up -d
```

### 3. Logs einsehen
```bash
docker compose logs -f polaris-bot-proto
```

---

## 🔬 Testen des Geofencing-Workflows

1. Starte den Stack via Docker Compose (die PostGIS-Datenbank initialisiert sich automatisch mit der `schema.sql`).
2. Führe das Skript `/database/cron_overpass.sh` aus, um die ersten Schul- oder Sektorengrenzen aus OpenStreetMap in die Datenbank zu laden.
3. Sende mit einem Matrix-Client (z. B. Element) ein standardisiertes Standort-Event (`m.location`) in den exklusiven, vordefinierten 1:1-Bot-Raum.
4. Beobachte im Docker-Log, wie das Gateway die Koordinate flüchtig prüft, sofort löscht und dein Smartphone geräuschlos in den entsprechenden Infospace einwählt.
