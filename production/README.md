# 🦀 POLARIS Production Gateway (Rust Layer)

Dieses Verzeichnis enthält die produktive, hochperformante und speichersichere Implementierung des **POLARIS Geo-Fencing Gateways** in Rust. 

Die Applikation ist als autonomer Microservice konzipiert, der für den Dauereinsatz in universitären Rechenzentren optimiert ist. Er verarbeitet Standort-Events parallel über thread-sichere In-Memory-Strukturen, gleicht sie flüchtig im RAM ab und steuert das geräuschlose *Auto-Join*-Verfahren über föderierte Matrix-Infospaces.

---

## 🛠️ Technologie-Stack

* **Runtime:** `tokio` (Asynchroner Multi-Thread-Executor)
* **Matrix-Protokoll:** `matrix-sdk` (Native Client-Föderationslogik)
* **Datenbank-Treiber:** `sqlx` (Asynchrone, zur Kompilierzeit typprüfende PostGIS-Anbindung)
* **RAM-Caching:** `dashmap` (Thread-sichere, parallele In-Memory-Hashmaps für maximale Performance ohne Garbage-Collection-Laufzeiten)

---

## 🏗️ Kompilierung & Entwicklung

Da SQLx die SQL-Abfragen während des Kompilierens auf syntaktische Korrektheit prüft, stehen zwei Build-Modi zur Verfügung:

### 1. Online-Modus (Lokale Entwicklung)
Wenn du aktiv am Code arbeitest und deine lokale PostGIS-Datenbank (z. B. via Docker Compose) im Hintergrund läuft.

1. Erstelle eine `.env`-Datei in diesem Verzeichnis:
   ```text
   DATABASE_URL=postgres://polaris:safe_password@127.0.0.1:5432/polaris_geo
   ```
2. Kompiliere oder starte das Projekt:
   ```bash
   cargo check
   cargo run
   ```

### 2. Offline-Modus (CI/CD Pipelines & Rechenzentrum)
Für Builds in Umgebungen, in denen während des Kompilierens keine Live-Datenbank erreichbar ist. Die Metadaten werden aus dem lokalen SQLx-Cache (`sqlx-data.json`) gelesen.

1. Installiere das SQLx-CLI einmalig global:
   ```bash
   cargo install sqlx-cli
   ```
2. Generiere den Query-Cache bei laufender Docker-Datenbank:
   ```bash
   DATABASE_URL=postgres://polaris:safe_password@127.0.0.1:5432/polaris_geo cargo sqlx prepare
   ```
3. Setze die Umgebungsvariable für den compilerseitigen Offline-Zwang:
   ```bash
   export SQLX_OFFLINE=true
   cargo build --release
   ```

---

## 📦 Docker-Deployment

Für den produktiven Betrieb wird ein sicheres **Multi-Stage Dockerfile** verwendet. Das finale Image basiert auf `debian-slim`, enthält keinerlei Compiler-Ballast und wird unter einem unprivilegierten System-User ausgeführt.

### 1. Image bauen
```bash
docker build -t matrix-polaris-gateway:latest .
```

### 2. Container ausführen
Übergebe die Konfigurationen und Passwörter beim Start flexibel als Umgebungsvariablen:

```bash
docker run -d \
  --name polaris-production-bot \
  --restart unless-stopped \
  -e BOT_PASSWORD="DeinStrengGeheimesMatrixPasswort" \
  -e DATABASE_URL="postgres://polaris:safe_password@polaris-postgis-db:5432/polaris_geo" \
  matrix-polaris-gateway:latest
```

---

## 🔒 Security & Performance-Vorgaben

* **Garbage Collector Freiheit:** Rust gibt den belegten RAM-Speicher dechiffrierter GPS-Koordinaten auf Hardwareebene sofort nach dem `ST_Contains`-Match wieder frei. Es verbleiben keine Datenfragmente im System.
* **Asynchroner Parallelismus:** Durch den Einsatz von `DashMap` blockieren sich hunderte gleichzeitige Nutzer-Events bei der Zellenprüfung nicht gegenseitig.
