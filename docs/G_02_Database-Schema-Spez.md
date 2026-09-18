# POLARIS-Gateway – Datenbank-Schema-Spezifikation

* **Projekt-ID:** matrix-polaris
* **Komponente:** matrix-polaris-gateway (Database Layer)
* **Version:** 1.0.0 (Prototyp-Spezifikation)
* **Lizenz:** MIT-Lizenz (Open Source)
* **Status:** IMPLEMENTED PROTOTYPE (Das relationale Schema und die Import-Skripte sind in Python & PostGIS lauffähig umgesetzt)

---

## 1. Architektur des Datenmodells

Das POLARIS-Datenmodell nutzt ein relationales 4-Tabellen-Hybridmodell. Es verbindet die amtlichen, administrativen Grenzen des Bundesamtes für Kartographie und Geodäsie (BKG / Datensatz VG25) mit feingranularen OpenStreetMap-Daten (OSM).

Das primäre Ziel des Schemas ist eine ressourcenschonende, kaskadierte Geofencing-Abfrage (Punkt-in-Polygon-Suche) zur automatisierten Zuweisung von Matrix-Raum-IDs.

---

## 2. Mathematische Begründung und Performance

Um Latenzen im Millisekundenbereich zu garantieren, ist das Datenmodell für ein vollständiges Caching im Arbeitsspeicher optimiert.

* **Datenvolumen im RAM:** Der bereinigte Geodatensatz für die Bundesrepublik Deutschland (Gemeinde- und Ortsteilebene inklusive Koordinaten-Polygonen) umfasst ein geschätztes Gesamtvolumen von ca. 250–300 MB. Dieser Datensatz passt vollständig in den Arbeitsspeicher-Cache (`shared_buffers`) einer standardmäßigen PostgreSQL-Instanz.
* **Indexierung:** Alle Geometriespalten (`geometry`) sind mit einem räumlichen **GiST-Index (Generalized Search Tree)** ausgestattet. Dies reduziert die Komplexität der Punkt-in-Polygon-Suche von einer linearen Prüfung `$O(n)$` auf eine logarithmische Suche `$O(\log n)$`.
* **Abfragegeschwindigkeit:** Durch die Kombination aus RAM-Caching und GiST-Indexierung liegen die Antwortzeiten für die zweistufige kaskadierte Geofencing-Abfrage im lokalen Testaufbau stabil unter **0,2 Millisekunden**.

---

## 3. Die Tabellenstrukturen im Detail

Das Schema gliedert sich in die administrativen Raumeinheiten und die zustandsbasierte Verwaltungsschicht des Gateways.

### 3.1 Hauptzonen (`main_zones`)

Speichert die offiziellen Gemeinde- und Stadtgrenzen (admin_level 8) basierend auf dem BKG-VG25-Datensatz.

* `ars_code` (VARCHAR, Primary Key): Der Amtliche Regionalschlüssel (z. B. `03153005` für Clausthal-Zellerfeld).
* `name` (VARCHAR): Offizieller Name der Gemeinde.
* `geometry` (GEOMETRY, MultiPolygon, SRID 4326): Die geografische Grenze.

### 3.2 Subzonen (`sub_zones`)

Speichert feingranulare Ortsteile, Dörfer, Stadtbezirke (admin_level 9/10) oder temporäre Sonderzonen (z. B. Gefahrenbereiche). Die Daten stammen primär aus OpenStreetMap via Overpass-API.

* `ars_code` (VARCHAR, Primary Key): Zusammengesetzter Schlüssel. Bei offiziellen Stadtteilen der ARS, bei OSM-Sonderstrukturen ein synthetischer Schlüssel aus `MutterARS_OSMID`.
* `parent_ars` (VARCHAR, Foreign Key -> `main_zones.ars_code`): Kaskadierende Verknüpfung zur übergeordneten Gemeinde.
* `name` (VARCHAR): Name des Ortsteils oder der Zone.
* `geometry` (GEOMETRY, MultiPolygon, SRID 4326): Die geografische Grenze. Bei reinen OSM-Punkten (Nodes) wird automatisiert ein kreisförmiger Geofencing-Puffer von 1.500 Metern (`ST_Buffer`) generiert.

### 3.3 Matrix-Räume (`polaris_spaces`)

Verknüpft die geografischen Zonen mit den tatsächlichen Räumen auf dem Matrix-Homeserver.

* `space_id` (VARCHAR, Primary Key): Die offizielle Matrix-Raum-ID (z. B. `!abcde:matrix.behörde.de`).
* `ars_code` (VARCHAR, Foreign Key): Verweis auf die zugewiesene Haupt- oder Subzone.
* `space_type` (VARCHAR): Definiert den Raumtyp (`COMMUNITY` für Bürgerkanäle, `EMERGENCY` für reine Warnkanäle).

### 3.4 Hysterese-Verwaltung (`exit_pending_users`)

Die Zustandsschicht des Gateways zur Vermeidung von permanenten Raumwechseln bei ungenauem GPS-Signal an Zonengrenzen.

* `user_id` (VARCHAR, Primary Key): Die Matrix-User-ID (z. B. `@buerger:matrix.de`).
* `current_ars` (VARCHAR): Die Zone, die der Nutzer rein rechnerisch verlassen hat.
* `exit_timestamp` (TIMESTAMP WITH TIME ZONE): Der exakte Zeitpunkt des Verlassens. Das Gateway nutzt diesen Wert, um eine Karenzzeit (Hysterese) von 10 Minuten abzuprüfen, bevor der endgültige `leave`-Befehl abgesetzt wird.

---

## 4. Die zweistufige kaskadierte SQL-Abfrage

Um die Geofencing-Prüfung hocheffizient zu gestalten, führt das Gateway die Punkt-in-Polygon-Suche in zwei Schritten aus:

```sql
-- Schritt 1: Ermittlung der primären Hauptzone (Gemeinde)
SELECT ars_code, name 
FROM public.main_zones 
WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326));

-- Schritt 2: Gezielter Drilldown in die Subzonen der ermittelten Gemeinde
SELECT ars_code, name 
FROM public.sub_zones 
WHERE parent_ars = :parent_ars 
  AND ST_Contains(geometry, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326));
```

Durch die Einschränkung der zweiten Stufe auf `parent_ars = :parent_ars` muss PostGIS das Koordinatenpaar nicht gegen tausende bundesweite Ortsteile prüfen, sondern exakt gegen die wenigen Subpolygone der bereits bekannten Gemeinde.