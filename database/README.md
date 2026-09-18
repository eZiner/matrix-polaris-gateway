# POLARIS-Gateway - Database Layer & Data Pipeline

Diese Komponente bildet das datenbankseitige und mathematische Fundament des POLARIS-Frameworks. Sie stellt das relationale Datenmodell bereit, verwaltet den automatisierten Import von geografischen Quelldaten und simuliert die kaskadierte Geofencing-Logik über eine Terminal-Schnittstelle.

* **Status:** IMPLEMENTED PROTOTYPE (Das PostGIS-Schema, die Import-Pipeline und die Test-CLI sind vollständig funktionsfähig implementiert. Es besteht in dieser Phase noch keine aktive Live-Kopplung an einen Matrix-Homeserver.)
* **Technologiestack:** PostgreSQL (Version 14+), PostGIS-Erweiterung, Python 3.10+ (GeoPandas, Psycopg2, Requests, Urllib3)

---

## 1. Datenbasis und hybride Datenbeschaffung

Um ein performantes und rechtlich verlässliches Geofencing zu ermöglichen, kombiniert die Import-Pipeline zwei unterschiedliche Datenquellen zu einem einheitlichen topologischen Modell:

1. **Amtliche administrative Grenzen (Basis-Layer):**
   * **Quelle:** Bundesamt für Kartographie und Geodäsie (BKG), Datensatz *VG25* (Gemeinden und Städte).
   * **Zweck:** Stellt die rechtlich verlässlichen, amtlichen Gemeindegrenzen und den offiziellen Amtlichen Regionalschlüssel (ARS) auf Ebene 8 (`admin_level=8`) bereit.
2. **Freie Geodaten (Feingranularer Layer):**
   * **Quelle:** OpenStreetMap (OSM) über die öffentliche Overpass-API.
   * **Zweck:** Liefert feingranulare Ortsteile, Dörfer und Stadtbezirke (`admin_level=9` oder `10`), die den amtlichen BKG-Gemeinden untergeordnet sind.
   * **Schlüssel-Synthese:** Da OSM-Ortsteile oft keinen offiziellen ARS-Code besitzen, generiert die Pipeline beim Import automatisch einen eindeutigen, synthetischen Universalschlüssel im Format `MutterARS_OSMID` (z. B. `03153005_1234567`), um die relationale Integrität zu wahren.

---

## 2. Bezug der amtlichen BKG-Basisdaten

Für die Initialisierung des Basis-Layers wird die offizielle Geogebiets-Datenbank der Bundesrepublik Deutschland benötigt.

1. Besuche das offizielle Open-Data-Portal des BKG (oder den gdz.bkg.bund.de-Server).
2. Lade den aktuellen Datensatz **Verwaltungsgebiete 1:25 000 (VG25)** herunter.
3. **Wichtig:** Wähle als Datenformat zwingend **GeoPackage (.gpkg)** und als Koordinatenreferenzsystem **UTM32 / ETRS89** (oder das Standard-WGS84, falls verfügbar).
4. Platziere die heruntergeladene Datei (z. B. `DE_VG25.gpkg`) in deinem System und hinterlege den absoluten Pfad in der `.env`-Datei (siehe Punkt 4.2).

---

## 3. Struktur des Quellcodes (`/database`)

Das Verzeichnis enthält die folgenden Kernkomponenten:

* `schema.sql`: Das relationale 4-Tabellen-Design inklusive Fremdschlüssel-Kaskaden (`ON DELETE CASCADE`), Hysterese-Tabellen und den für den RAM-Betrieb optimierten räumlichen GiST-Indizes (`USING gist (geometry)`).
* `import_gpkg.py`: Initialisiert die Datenbank. Lädt das amtliche BKG-GeoPackage, extrahiert alle administrativen Einheiten (Bundesländer, Landkreise, Gemeinden) und projiziert deren Geometrien standardisiert in das globale GPS-Format WGS84 (EPSG:4326), um sie in die Tabellen `main_zones` einzupflegen.
* `import_one_osm_subzone.py`: Der automatische Importer für hyperlokale Ortsteile. Er fragt Daten via Overpass-API ab, validiert über einen PostGIS-Check (`ST_Contains`), ob die gelieferten Punkte real innerhalb der BKG-Muttergemeinde liegen, und versieht punktförmige Siedlungen (OSM Nodes) mit einem mathematischen Geofencing-Schutzradius von 1.500 Metern mittels `ST_Buffer`. Enthält eine integrierte API-Drosselungs-Sicherung (automatische Retries mit exponentiellem Backoff bei HTTP 429).
* `sync_multipolygons.py`: Ein Hilfsmodul für den OSM-Importer. Es ruft lose Linienketten (Ways) unvollständiger OSM-Relationen ab und schließt sie direkt auf der Datenbank über die PostGIS-Funktionen `ST_Polygonize` und `ST_Multi` zu sauberen Flächenpolygonen zusammen. Fängt Programmabbrüche (`Strg+C`) sauber auf und schließt Ressourcen ohne Datenkorruption.
* `cli_manager.py`: Ein interaktives Terminal-Werkzeug, mit dem Entwickler durch die importierte Verwaltungshierarchie navigieren und über statische X/Y-Koordinaten die zweistufige PostGIS-Geofencing-Kaskade lokal testen können.
* `test_geofence.py`: Ein schlanker Kern-Prüfstand für Geofencing-Abfragen, optimiert für maximale Plattformkompatibilität (z. B. unter Windows/WSL), indem er ohne erweiterte Cursor-Abhängigkeiten direkt auf die PostGIS-Indizes zugreift, um Indexierungsfehler zu vermeiden.

---

## 4. Lokales Setup und Inbetriebnahme

### 4.1 Voraussetzungen

Stelle sicher, dass eine PostgreSQL-Instanz läuft und die PostGIS-Erweiterung aktiv ist:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 4.2 Umgebungsvariablen (`.env`)

Kopiere das bereitgestellte Template `.env.example` als `.env` in dein Arbeitsverzeichnis und passe die Verbindungsinformationen sowie den absoluten Pfad zum BKG-Datensatz an:

```env
# 1. POSTGIS DATENBANK-VERBINDUNG
# Format: postgres://username:password@hostname:port/database_name
DATABASE_URL=postgres://polaris_user:dein_sicheres_passwort@localhost:5432/polaris_db

# 2. AMTLICHE BKG-GEODATEN (VG25)
# Absoluter Pfad zur heruntergeladenen 'DE_VG25.gpkg' Datei im UTM32N-Format.
BKG_GPKG_PATH=/var/polaris/database/DE_VG25.gpkg
```

### 4.3 Python-Abhängigkeiten installieren

Installiere die benötigten Bibliotheken für die Daten-Pipeline:

```bash
pip install -r requirements.txt
```

*(Hinweis: Unter Windows wird die Installation von Fiona/Shapely/GeoPandas über* `pip` *durch vorkompilierte Wheels erleichtert, falls C++-Compiler-Fehler auftreten).*

### 4.4 Datenbank initialisieren und Schema einspielen

Erstelle die leere Ziel-Datenbank und spiele die Tabellenstrukturen ein:

```bash
psql -U polaris_user -d polaris_db -f schema.sql
```

#### ⚠️ WICHTIG: Fehlerbehebung für Windows-Nutzer unter WSL1

Falls du den Prototypen unter **WSL1 (Windows Subsystem for Linux 1)** betreibst, schlagen reguläre Befehle wie `CREATE DATABASE` oder `DROP DATABASE` aufgrund von Emulationsfehlern im POSIX-Dateisystem von PostgreSQL oft fehl.

Sollte dieser Fehler auftreten, stoppe den Dienst und erzwinge die administrativen Schritte (Datenbank-Erstellung und Schema-Import) im **Single-User-Modus** direkt über die Binärdateien (Beispiel für PostgreSQL 14):

```bash
# 1. Laufenden PostgreSQL-Dienst stoppen
sudo service postgresql stop

# 2. Datenbank im Single-User-Modus erzwingen
sudo -u postgres /usr/lib/postgresql/14/bin/postgres --single -D /var/lib/postgresql/14/main -c config_file=/etc/postgresql/14/main/postgresql.conf postgres <<< "CREATE DATABASE polaris_db;"

# 3. Dienst wieder regulär starten
sudo service postgresql start

# 4. PostGIS-Erweiterung und Rechte-Inhaberschaft zuweisen
sudo -u postgres psql -d polaris_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -c "ALTER DATABASE polaris_db OWNER TO polaris;"

# 5. Schema einspielen (als Superuser postgres ausführen)
sudo -u postgres psql -d polaris_db -f schema.sql
```

*Hinweis zum Datenbank-Löschen:* Falls du die gesamte Datenbank später löschen oder zurücksetzen möchtest (`DROP DATABASE`), musst du **exakt genauso verfahren** (Dienst stoppen, Befehl im `--single`-Modus absetzen, Dienst starten), da WSL1 den Löschvorgang im laufenden Service-Betrieb sonst mit einem Dateisystem-Fehler blockiert. Passe zudem die Versionsnummer `14` im Pfad ggf. an deine installierte PostgreSQL-Version an.

### 4.5 Die Daten-Pipeline ausführen

1. **Amtliche Basisdaten laden:**
   Liest die Geometrien der Bundesländer, Landkreise und Gemeinden ein und baut das administrative Grundgerüst:

   ```bash
   python import_gpkg.py
   ```
2. **Hyperlokale Ortsteile aus OSM nachladen:**
   Fragt die detaillierten Ortsteile für eine spezifische Gemeinde ab. Übergib hierzu den Amtlichen Regionalschlüssel (ARS), den du im ersten Schritt importiert hast:

   ```bash
   python import_one_osm_subzone.py --ars 03153005
   ```

   *Tipp: Der Importer hält automatisch Fair-Use-Pausen von 5 Sekunden zwischen Abfragen ein, um die öffentlichen Overpass-Server nicht zu überlasten.*

---

## 5. Geofencing lokal testen und simulieren

Um die mathematische Kaskade und die korrekte Zuordnung der simulierten Matrix-Räume ohne echten Server-Verbund zu testen, stehen zwei Werkzeuge bereit:

### 5.1 Interaktiver CLI-Manager

Ermöglicht das komfortable Durchsuchen der Hierarchie und das Abfragen von Koordinaten per Tastatur-Navigation:

```bash
python cli_manager.py
```

### 5.2 Core Geofencing-Prüfstand (Stufe 1 & 2)

Ein dediziertes Testskript zur reinen Performance- und Index-Validierung. Übergib Längen- und Breitengrad direkt als Argumente, um die PostGIS-Antwortzeit zu messen:

```bash
python test_geofence.py --lon 10.3341 --lat 51.8105
```

Das Skript gibt bei erfolgreichem Index-Match die ermittelte Hauptgemeinde sowie das exakte Ortsteil-Subpolygon oder den 1500m-Kreispuffer inklusive der theoretischen Matrix-Raum-ID aus.

- 

---

## 👥 Mitmachen & Community

POLARIS versteht sich als gesamtgesellschaftliches Infrastrukturprojekt für die digitale Souveränität im kommunalen Raum. Wir laden Entwickler, Netzwerk-Architekten, Kommunalpolitiker und Verwaltungs-Spezialisten herzlich ein, an den Konzepten und der Implementierung mitzuwirken.

---

## ⚠️ Status des Projekts & Haftungsausschluss

**Dieses Projekt ist ein privater, nicht-kommerzieller Prototyp (Proof of Concept).**

Bitte beachten Sie für die Nutzung und Weiterentwicklung folgende Punkte:

- **Entwicklungsstatus:** Diese Software befindet sich im Prototypen-Stadium. Sie ist NICHT für den produktiven Einsatz bereit und sollte ohne vorherige, unabhängige Sicherheitsprüfungen nicht in Live-Systemen eingesetzt werden.
- **KI-Unterstützung:** Teile dieses Codes und der Dokumentation wurden mit Unterstützung von Google-KI-Werkzeugen erstellt. Alle Inhalte wurden vom Autor manuell geprüft, überarbeitet und getestet. Eine absolute Fehlerfreiheit kann jedoch nicht garantiert werden.
- **Haftungsausschluss:** Entsprechend der MIT-Lizenz wird die Software ohne jegliche Gewährleistung ("as is") zur Verfügung gestellt. Der Autor übernimmt keine Haftung für Systemfehler, Datenverlust, Sicherheitslücken oder etwaige Lizenzkonflikte durch eingebundene Pakete (Dependencies).
- **Zukünftige Trägerschaft:** Dieses Repository dient als technische Grundlage. Es ist vorgesehen, dass die finale redaktionelle, technische und rechtliche Verantwortung sowie die Code-Audits vor einem produktiven Rollout an eine öffentliche Institution oder eine gemeinnützige Organisation (NGO) übertragen werden.