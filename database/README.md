# POLARIS Gateway - Relationales Geofencing & Daten-Infrastruktur

Dieses Verzeichnis enthält die Kern-Pipeline für das raumbezogene Datenmanagement des POLARIS-Gateways. Die Architektur paart die offiziellen, hochauflösenden Verwaltungsgrenzen des **Bundesamtes für Kartographie und Geodäsie (BKG)** mit den feingranularen, dynamischen Ortsteil-Informationen aus **OpenStreetMap (OSM)** zu einem hybriden, elastischen Geofencing-System.

---

## 🗺️ Das hybride Datenmodell

Um eine lückenlose und performante Standort-Zugehörigkeit im Matrix-Netzwerk zu garantieren, kombiniert POLARIS zwei Datenquellen in einer zentralen PostGIS-Tabelle (`public.polaris_infospaces`):

1. **BKG (VG25)**: Liefert die rechtsverbindlichen, mathematisch exakten Grenzen für Bundesländer, Landkreise und Gemeinden (`admin_level 8`). Diese bilden das stabile "Rathaus-Dach" und verwalten die administrativen IDs (Amtlicher Regionalschlüssel - ARS).
2. **OpenStreetMap (OSM)**: Ergänzt die Struktur um hyperlokale Identitäten auf Ebene von Ortsteilen, Bezirken und eingemeindeten Städten (`admin_level 9/10`) sowie reine Wohnplatz-Knotenpunkte (Nodes). Wenn OSM keinen ARS besitzt, generiert die Pipeline eine unzerstörbare Kombination aus Mutter-ARS und OSM-Relation-ID (`MutterARS_OSMID`).

---

## 🛠️ 1. PostgreSQL / PostGIS Datenbank einrichten

POLARIS benötigt eine PostgreSQL-Datenbank mit nativer Geo-Erweiterung.

### Lokales Setup (z.B. unter Windows/WSL oder Docker)

1. **Erzeuge die Datenbank** über dein bevorzugtes SQL-Tool (pgAdmin, DBeaver) oder das Terminal:
   ```sql
   CREATE DATABASE polaris_db;
   ```
2. **Aktiviere die PostGIS-Erweiterung**:
   Das Initialisierungs-Skript führt diesen Schritt automatisch aus. Manuell lautet der Befehl:
   ```sql
   \c polaris_db;
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
3. **Umgebungsvariablen konfigurieren**:
   Erstelle oder ergänze die Datei `production/.env` im Projektverzeichnis:
   ```text
   DATABASE_URL=postgres://dein_user:dein_passwort@localhost:5432/polaris_db
   BKG_GPKG_PATH=G:/projects/polaris/matrix-polaris-gateway/database/vg25_utm32/DE_VG25.gpkg
   ```

---

## 📦 2. Bezug der amtlichen BKG-Basisdaten (VG25)

Die hochauflösenden, offiziellen Verwaltungsgrenzen Deutschlands werden vom BKG als Open Data zur Verfügung gestellt.

1. Besuche das offizielle **BKG Open Data Center**.
2. Navigiere zu den Produkten: **Verwaltungsgebiete 1:25.000 (VG25)**.
3. Lade das Paket im **GeoPackage-Format (.gpkg)** für das Koordinatensystem **UTM32N** herunter (Dateiname entspricht meist `DE_VG25.gpkg`).
4. Entpacke die Datei und lege sie in deinem lokalen Projektpfad ab (Pfad in der `.env` als `BKG_GPKG_PATH` hinterlegen).

---

## 🚀 3. Die Skripte und ihre Ausführung

Führe die Skripte immer im Kontext der konfigurierten virtuellen Umgebung (`prototype/.venv`) aus.

### Schritt A: Die BKG-Basisdaten initialisieren
Das Skript bereitet die Haupttabelle vor, setzt die Primärschlüssel-Spalte zukunftssicher auf `VARCHAR(50)` für OSM-Kombis um, importiert die reinen Text-Namenslisten für Länder/Kreise (RAM-schonend via `ignore_geometry`) und streamt die Geometrien der Gemeinden per Bulk-Upload nach PostGIS. Alte Testdaten werden sicher per `TRUNCATE` entfernt.
```bash
prototype\.venv\Scripts\python.exe database/import_gpkg.py
```

### Schritt B: Lokaler OSM-Ortsteil-Drilldown (Test-CLI)
Ein hochpräzises Werkzeug, um eine spezifische Gemeinde (Eingabe via Name oder ARS, z.B. *Clausthal-Zellerfeld*) zu analysieren.
* Extrahiert das echte, umschließende Grenzpolygon der Gemeinde aus PostGIS und vereinfacht es elastisch (`ST_Simplify`), um die Overpass-API nicht zu überlasten.
* Fragt Overpass einzeilig ohne sperrige Zeilenumbrüche ab und schneidet Nachbarbundesländer mathematisch exakt an der Grenze ab (`poly:"..."`-Filter).
* Erfasst sowohl Grenz-Relationen als auch reine Punkt-Ortsteile (Nodes wie *Buntenbock* oder *Torfhaus*) und verpasst Nodes per PostGIS einen **1.500 Meter Geofencing-Schutzradius** (`ST_Buffer`).
* Unterstützt die interaktiven Steuerungsmodi: **1** (Nur anzeigen), **2** (Importieren wenn neu), **3** (Löschen & Überschreiben).
```bash
prototype\.venv\Scripts\python.exe database/import_one_osm_subzone.py
```

### Schritt C: Der interaktive Beziehungs-Manager (CLI-Drilldown)
Ermöglicht das Navigieren durch die importierte relationale Struktur direkt im Terminal. Es nutzt performante SQL-Joins über die neuen Nachschlagetabellen (`bkg_lan_names` / `bkg_krs_names`) und schneidet die hierarchischen IDs live per `SUBSTR(ars_code, 1, X)` aus dem Primärschlüssel heraus – komplett frei von hardcodierten Texten. Holt am Ende das hochauflösende WKT-Polygon live aus PostGIS.
```bash
prototype\.venv\Scripts\python.exe database/cli_manager.py
```

---

## 📂 4. Verzeichnisstruktur & Archiv

*   `import_gpkg.py` ➔ Der zentrale, kombinierte BKG-Initializer (Länder, Kreise, Gemeinden).
*   `import_one_osm_subzone.py` ➔ Modularer Hybrid-Importer (OSM Relationen + gepufferte Nodes).
*   `cli_manager.py` ➔ Relationales Navigations- und Kontrollwerkzeug für das Terminal.
