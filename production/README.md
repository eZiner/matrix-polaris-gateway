# 🦀 POLARIS Production Gateway (Rust Layer)

Das **POLARIS Matrix Geofence Gateway** ist eine hochperformante, in **Rust** entwickelte Infrastrukturkomponente, die Live-Standortdaten (`m.location`) von Matrix-Nutzern mit einer lokalen **PostGIS-Datenbank** verknüpft, um Bürger automatisch regionalen Matrix-Räumen zuzuordnen oder beim Verlassen zu entfernen.

---

## 🛠️ Technologie-Stack

* **Runtime:** `tokio` (Asynchroner Multi-Thread-Executor)
* **Matrix-Protokoll:** `matrix-sdk` (v0.19 – Föderationslogik und E2E-Verschlüsselung)
* **Datenbank-Treiber:** `sqlx` (Asynchrone PostGIS-Anbindung)
* **RAM-Caching:** `dashmap` / `std::collections` (Thread-sichere In-Memory-Strukturen)

---

## 🏗️ System-Architektur & Betriebsmodi

Die Steuerung erfolgt über das Umgebungsvariablen-Flag `POLARIS_TEST_MODE` in der `.env`:

### 1. Simulationsmodus (`POLARIS_TEST_MODE=true`)
* Läuft unabhängig ohne Synapse-Server, spult vordefinierte Bewegungsprofile ab und gibt Netzwerkbefehle als Logs auf der Konsole aus.

### 2. Produktivmodus (`POLARIS_TEST_MODE=false`)
* Baut eine permanente HTTP-Long-Polling-Verbindung zum Synapse-Server auf, filtert gezielt nach Standort-Events und unterstützt Multi-User-Handling über Tokio-Tasks.

---

## 🧠 Kern-Algorithmen & Logiken

* **Zweistufige PostGIS-Kaskade (`geofence.rs`):** Evaluiert über räumliche SQL-Indizes (`ST_Contains`) die Hauptzone (z. B. via VG25-Geodaten) und Subzonen (OpenStreetMap-Knoten-Matching).
* **Multi-User-Hysterese:** Verhindert GPS-Flackern an Zonengrenzen durch eine flüchtige In-Memory-Warteliste (sofortiger Eintritt, 10 Minuten Cooldown beim Austritt zur Vermeidung von Leave/Join-Rauschen).
---

## 🏗️ Kompilierung & Entwicklung im Rechenzentrum

Für den Betrieb stehen je nach Umgebung zwei Build-Verfahren zur Verfügung:

### 1. Online-Modus (Lokale Entwicklung)
Bei erreichbarer Live-Datenbank im Hintergrund:
```bash
cargo check
cargo run --bin matrix-polaris-gateway
```

### 2. Offline-Modus (CI/CD Pipelines)
Für isolierte Umgebungen ohne Live-Datenbank via `sqlx-data.json`-Cache:
1. **SQLx-CLI installieren:** `cargo install sqlx-cli --no-default-features --features postgres`
2. **Cache generieren:** `DATABASE_URL=postgres://... cargo sqlx prepare`
3. **Bauen:** `export SQLX_OFFLINE=true && cargo build --release`

---

## 📦 Docker-Deployment

Es wird ein speichereffizientes **Multi-Stage Dockerfile** auf Basis von `debian-slim` ohne Compiler-Ballast genutzt, ausgeführt unter einem unprivilegierten System-User.

* **Image bauen:** `docker build -t matrix-polaris-gateway:latest .`
* **Container starten:** Dynamische Injektion von Umgebungsvariablen (`POLARIS_TEST_MODE`, `DATABASE_URL`, `MATRIX_HOMESERVER`, etc.) via `docker run -d ...`

---

## 🔒 Performance-Garantien & BSI-Konformität

* **Garbage-Collector-Freiheit:** Sofortige Freigabe von Speicher auf Hardwareebene nach Verarbeitung.
* **Stateful Session-Management:** Verschlüsselte Sicherung der Krypto-Sitzung in `.matrix_session.json`.
* **Behördensichere E2EE:** Kryptografische Schlüsselverwaltung über das `sqlite`-Feature des `matrix-sdk` in einer lokalen `polaris_crypto_store.db`.
