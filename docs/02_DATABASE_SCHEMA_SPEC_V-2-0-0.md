**POLARIS – Technische Spezifikation des Datenmodells (PostGIS)**

**Das relationale 4-Tabellen-Hybridmodell für hochperformantes, dezentrales Geofencing**

**Version:** 2.0.0  
**Status:** ARCHITECTURE CERTIFIED (Synchronisiert mit den neuesten Import-Skripten)  
**Zugehöriges Schema:** `database/schema.sql`  
**Zeitstempel:** Freitag, 11. September 2026

---

**💾 1. Das relationale 4-Tabellen-Design**

Um die Geometrie-Berechnungen (Zustandsschicht) strikt von der Matrix-Raum-Logik (Kommunikationsschicht) zu trennen, nutzt jeder autonome POLARIS-Rathausknoten eine PostgreSQL-Datenbank mit aktivierter PostGIS-Erweiterung.

Das Schema besteht aus vier eng verzahnten Tabellen. Es kombiniert die amtliche, rechtssichere Struktur des Bundesamtes für Kartographie und Geodäsie (BKG) mit den feingranularen Community-Daten aus OpenStreetMap (OSM) und erlaubt eine hocheffiziente, zweistufige Kaskadenabfrage sowie unregelmäßige Freiform-Sonderzonen.

```
  +-----------------------+              +-----------------------+

  |      main_zones       |              |       sub_zones       |
  +-----------------------+              +-----------------------+

  | PK  ars_code          |<----+        | PK  ars_code          |
  |     zone_name         |     |        | FK  parent_ars        |
  |     geometry (MPoly)  |     |        |     geometry (Geom)   |
  +-----------------------+     |        +-----------------------+
              │                 |                    │
              │ 1:N             │ 1:1 / 1:N          │ 1:N
              ▼                 │                    ▼
  +-----------------------+     │        +-----------------------+

  |    polaris_spaces     |     │        |   space_assignments   |
  +-----------------------+     │        +-----------------------+

  | PK  matrix_space_id   |     +--------| PK  matrix_space_id   |
  | FK  ars_code          |              | PK  ars_code          |
  |     geometry (MPoly)  |              +-----------------------+
  +-----------------------+
```

**A. Tabelle:** `public.main_zones`

Enthält die offiziellen, administrativen Verwaltunggrenzen der Bundesrepublik Deutschland auf Gemeinde-Ebene (`admin_level = 8`). Jedes Rathaus importiert diese Tabelle vollständig für ganz Deutschland via BKG-GeoPackage (VG25) \[1.21\].

- `ars_code` (`VARCHAR(50) / PRIMARY KEY`): Der Amtliche Regionalschlüssel (ARS) als eindeutiger Identifikator.
- `zone_name` (`VARCHAR(255)`): Menschenlesbarer Name der Gemeinde (z. B. "Clausthal-Zellerfeld").
- `admin_level` (`INT / DEFAULT 8`): Festgelegt auf die Gemeinde-Ebene.
- `bundesland` / `landkreis` (`VARCHAR`): Administrative Zuordnungen für den CLI-Drilldown.
- `is_polaris_space` (`BOOLEAN / DEFAULT FALSE`): Kennzeichnet, ob die jeweilige Kommunalverwaltung das POLARIS-System aktiv betreut (`TRUE`) oder die Zone im System noch unkoordiniert ist (`FALSE`).
- `geometry` (`geometry(MultiPolygon, 4326)`): Strikt erzwungene MultiPolygone im WGS84-Koordinatensystem. Garantiert maximale Performance des räumlichen GIST-Index \[1.21\].

**B. Tabelle:** `public.sub_zones`

Enthält feingranulare Ortsteile, Stadtbezirke (OSM `admin_level = 9/10`) sowie künstlich gepufferte Einzelsiedlungen (`admin_level = 11`), die keine eigene Kommunalverwaltung besitzen.

- `ars_code` (`VARCHAR(50) / PRIMARY KEY`): Generierter Kombi-Schlüssel im Format `MutterARS_OSMID` (z. B. `03153005_1234567`). Sichert die relationale Integrität, da OSM-Ortsteile selten eigene ARS-Codes besitzen.
- `parent_ars` (`VARCHAR(50) / FOREIGN KEY REFERENCES main_zones(ars_code) ON DELETE CASCADE`): Die harte 1:n-Verknüpfung zur administrativ verantwortlichen Gemeinde.
- `zone_name` (`VARCHAR(255)`): Name des Ortsteils (z. B. "Buntenbock").
- `admin_level` (`INT`): `9/10` für echte OSM-Flächen-Relationen, `11` für punktförmige Siedlungen (Nodes) \[1.21\].
- `geometry` (`geometry(Geometry, 4326)`): Erlaubt MultiPolygone sowie durch Radien gepufferte Kreis-Polygone (`ST_Buffer`), falls ein Ortsteil in OSM nur als einzelner Punkt (Node) existiert.

**C. Tabelle:** `public.polaris_spaces`

Die Schnittstelle zur logischen Matrix-Raum-Struktur. Sie bildet ab, welche Matrix-Space-IDs existieren, wer die administrative Oberhoheit hat und hält eine jokerartige Freiform-Geometrie für ad-hoc Krisengebiete vor \[1.21\].

- `matrix_space_id` (`VARCHAR(255) / PRIMARY KEY`): Die eindeutige, kryptografische Matrix-Raum-Adresse (Format: `!raum_id:domain`) \[1.21\].
- `ars_code` (`VARCHAR(50) / FOREIGN KEY REFERENCES main_zones(ars_code) ON DELETE RESTRICT`): Verweist unumstößlich auf die politisch und rechtlich zuständige Gemeinde. Sie sichert, dass ein Rathaus nur eigene Räume manipulieren darf.
- `parent_space` (`VARCHAR(255)`): Bildet die hierarchische Schachtelung von Matrix-Spaces ab (Ordner-Strukturen).
- `is_space` (`BOOLEAN / DEFAULT FALSE`): `TRUE` = Übergeordneter Matrix-Space-Ordner (Kanalbündelung), `FALSE` = Dedizierter Chat-Raum / Warnkanal.
- `room_alias` (`VARCHAR(255)`): Menschenlesbare Matrix-Adresse (z. B. `#polaris_goslar:domain`) \[1.21, 1.27\].
- `geometry` (`geometry(MultiPolygon, 4326) / NULLABLE`): **Der funktionale Joker.** Standardmäßig leer (`NULL`). Wird bei Katastrophen (z. B. Giftgaswolken, Hochwasser-Einzugsgebieten) mit einem dynamischen Freiform-Polygon befüllt, das völlig unabhängig von administrativen Grenzen ausgewertet werden kann.

**D. Kreuztabelle:** `public.space_assignments`

Regelt die n:m-Beziehungen zwischen Räumen und Geozonen im Normalbetrieb (z. B. wenn eine Freiwillige Feuerwehr einen gemeinsamen Chat-Raum für zwei benachbarte Ortsteile betreibt).

- `matrix_space_id` (`VARCHAR(255) / FOREIGN KEY REFERENCES polaris_spaces(matrix_space_id) ON DELETE CASCADE`): Verweis auf den Matrix-Raum.
- `ars_code` (`VARCHAR(50)`): Kann sowohl auf eine Gemeinde (`main_zones`) als auch auf einen Ortsteil (`sub_zones`) verweisen.
- `PRIMARY KEY (matrix_space_id, ars_code)`

---

**⚡ 2. Die mathematische Begründung der Performance ("Deutschland im RAM")**

Kritiker dezentraler Architekturen bemängeln oft, dass ein lokaler Rathaus-Server (z. B. in einer 10.000-Einwohner-Gemeinde) überfordert ist, wenn er Geometriedaten für ganz Deutschland verarbeiten muss \[1.21\]. Diese Annahme ist im GIS-Bereich nachweislich falsch:

**A. Der Speicher-Fakten-Check**

Der vollständige BKG-Datensatz (VG25) aller rund 11.000 deutschen Gemeinden umfasst exakt \~11.000 Geometrie-Zeilen \[1.21\]. In einer PostgreSQL-Datenbank belegt dieser Datensatz inklusive Koordinatenpunkten gerade einmal ca. **250 bis 300 Megabyte** Speicherplatz \[1.21\].

- Jeder gängige Enterprise-Server des SLG-Racks (128 GB RAM) hält diesen gesamten Datensatz permanent im Arbeitsspeicher-Cache (`shared_buffers`) \[1.21\].
- Es finden beim Geofencing-Abgleich im Live-Betrieb **Null Festplatten-Schreib/Lesezugriffe (I/O)** auf den SSDs statt.

**B. Die GIST-Index-Skalierung (\\(O(\\log n)\\))**

PostGIS nutzt für räumliche Abfragen den GIST-Index (Generalized Search Tree) basierend auf R-Bäumen. Der Index umschließt komplexe Geometrien mit minimalen Rechtecken (*Bounding Boxes*).

- Bei einer GPS-Punkt-Abfrage (`ST_Contains`) muss PostGIS nicht 11.000 Polygone mathematisch berechnen.
- Der GIST-Index schließt über den Baum-Algorithmus innerhalb von Mikrosekunden 99,9 % aller deutschen Gemeinden aus. Nur die 1–2 exakt umschließenden Rechtecke des aktuellen Standorts werden einer echten mathematischen Punkt-in-Polygon-Prüfung unterzogen.
- **Resultat:** Die Abfragegeschwindigkeit für eine Koordinate am anderen Ende von Deutschland liegt auf dem lokalen Rathaus-Server stabil bei **unter 0,2 Millisekunden** \[1.21\]!

---

**🔍 3. Die zweistufige Geofencing-Abfrage (SQL-Muster)**

Wenn das lokale Rust-Gateway ein GPS-Signal empfängt, feuert es eine zweistufige, kombinierte Kaskadenabfrage ab, um die Last auf ein absolutes Minimum zu drücken. Der PostGIS-Index wird durch den impliziten Join in `matched_sub` gezielt nur auf die Ortsteile der bereits gematchten Gemeinde angewendet:

**sql**

```
-- GEOFENCING CORE-QUERY
-- Ermittelt parallel administrative Zonen, Ortsteile und aktive ad-hoc Krisenräume

WITH current_point AS (
    -- Die vom Smartphone via TLS gelieferte GPS-Koordinate
    SELECT ST_SetSRID(ST_MakePoint(10.33472, 51.80434), 4326) AS geom
),
matched_main AS (
    -- Stufe 1: Schneller Scan gegen die globalen Gemeinde-Hauptzonen
    SELECT m.ars_code, m.zone_name, m.admin_level 
    FROM public.main_zones m, current_point cp
    WHERE ST_Contains(m.geometry, cp.geom) AND m.is_polaris_space = TRUE
),
matched_sub AS (
    -- Stufe 2: Gezielter Drilldown in die Sub-Zonen der gematchten Gemeinde
    SELECT s.ars_code, s.zone_name, s.admin_level
    FROM public.sub_zones s, current_point cp
    JOIN matched_main mm ON s.parent_ars = mm.ars_code
    WHERE ST_Contains(s.geometry, cp.geom)
),
matched_custom_spaces AS (
    -- Sonderstufe: Parallel-Check auf raumspezifische Freiform-Krisengeometrien (Joker)
    SELECT p.matrix_space_id, p.ars_code, 99 AS admin_level, 'KRISENZONE' AS zone_name
    FROM public.polaris_spaces p, current_point cp
    WHERE p.geometry IS NOT NULL AND ST_Contains(p.geometry, cp.geom)
)
-- Zusammenführung aller aktiven Räume, in die der User eingebucht werden muss
SELECT ars_code, zone_name, admin_level, NULL AS matrix_space_id FROM matched_main
UNION ALL
SELECT ars_code, zone_name, admin_level, NULL AS matrix_space_id FROM matched_sub
UNION ALL
SELECT ars_code, zone_name, admin_level, matrix_space_id FROM matched_custom_spaces;
```