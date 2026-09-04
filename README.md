# 🗺️ POLARIS Geofencing-Gateway (`matrix-polaris-gateway`)

POLARIS ist ein architektonisches Konzept für ein dezentrales, digital souveränes Bürgernetzwerk. Es ermöglicht Kommunen, standortbasierte Informations- und Katastrophenschutzräume geräuschlos und absolut datenschutzkonform via Matrix-Protokoll bereitzustellen.

Dieses Repository enthält das **Geo-Fencing Gateway**, das standardisierte Standort-Signale (`m.location`) flüchtig im Arbeitsspeicher auswertet und Bürger vollautomatisch via *Auto-Join* in regionale **Infospaces** ein- und ausklinkt.

---

## 🏛️ Die Architektur auf einen Blick

* **Die Rathaus-Verwaltung:** Bleibt als hochgesichertes internes Behördennetz eine unantastbare Festung. Sie greift nur kontrolliert von innen nach außen auf die DMZ zu.
* **Die Universitäts-DMZ:** Die kommunalen Matrix-Homeserver (z. B. `matrix.goslar.de`) stehen physisch in den Rechenzentren der Universitäten. Sie dienen als vorgelagerter Postkasten im öffentlichen Raum.
* **Die Bürger-Ebene:** Der Bürger nutzt genau ein einziges verifiziertes Konto (`@max:goslar.de`) in einem Standard-Messenger (wie Element) für den amtlichen Bürgerraum, die flüchtigen Infospaces und die weltweite freie Kommunikation.

Das genaue Schichtenmodell und die Protokoll-Spezifikationen findest du im Ordner [`/docs/`](./docs/).

---

## 📂 Verzeichnisstruktur

Das Repository ist als **Polyglot-Repository** aufgebaut, um die schnelle Entwicklung von Ideen strikt vom hochperformanten Rechenzentrums-Betrieb zu trennen:

* **`/prototype/` (Python):** Optimiert für schnelles Prototyping, Experimente und lokale Tests.
* **`/production/` (Rust):** Die produktive, speichersichere und hochperformante Version für den echten Dauereinsatz.
* **`/database/`:** PostGIS-Datenbankschemata und automatisierte Import-Skripte für OpenStreetMap (Overpass-Turbo).
* **`/docs/`:** Zentrale technische Dokumentation und Protokoll-Abläufe.

---

## 🚀 Inbetriebnahme

### 🐍 1. Prototyping (Python)
Ideal für die lokale Weiterentwicklung und schnelle Funktionstests. Der Bot lauscht ausschließlich im vordefinierten Bot-Raum und wertet Koordinaten flüchtig im RAM aus.

```bash
cd prototype/

# Image für die Entwicklung bauen
docker build -f Dockerfile.dev -t polaris-prototype:dev .

# Container mit Live-Code-Mount starten
docker run -d \
  --name polaris-proto-run \
  -v \$(pwd):/app \
  polaris-prototype:dev
```

### 🦀 2. Produktiver Betrieb (Rust)
Für den echten Einsatz im Universitäts-Rechenzentrum. Bietet maximale Thread-Sicherheit, parallele Verarbeitung via `DashMap` und läuft dank Multi-Stage-Docker-Build als minimales, hochsicheres und winziges Linux-Image.

```bash
cd production/

# Produktives Multi-Stage-Image bauen
docker build -t matrix-polaris-gateway:latest .

# Container im Live-Betrieb starten (Konfiguration via Umgebungsvariablen)
docker run -d \
  --name polaris-bot \
  --restart unless-stopped \
  -e BOT_PASSWORD="DeinSicheresPasswort" \
  matrix-polaris-gateway:latest
```

---

## 🔒 Datenschutz & Security (Privacy by Design)

1. **Keine Bewegungsprofile:** Die Dechiffrierung und der mathematische PostGIS-Abgleich (`ST_Contains`) erfolgen ausschließlich flüchtig im flüchtigen Arbeitsspeicher (RAM). Die exakten GPS-Daten werden sofort danach unwiderruflich gelöscht.
2. **Datenhygiene (Hysterese-Schutz):** Verlässt ein Bürger ein Polygon, greift ein 10-minütiger Cooldown. Erst danach erfolgt der automatische Server-Kick aus dem Infospace. Der Ordner verschwindet spurlos vom Smartphone, um Gruppenleichen im Messenger zu verhindern.
3. **Troll-Schutz:** Alle Räume sind über native Matrix `restricted` Join Rules an einen gemeinsamen universitären **Mutter-Space** gekoppelt. Externe Server (wie `matrix.org`) werden an der Föderationsgrenze automatisch abgewiesen.

---

## 📄 Lizenz

Dieses Infrastrukturprojekt ist als gesamtgesellschaftliche Daseinsvorsorge gemeinfrei und steht unter der [MIT-Lizenz](./LICENSE).
