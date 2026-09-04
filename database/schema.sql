-- =============================================================================
-- POLARIS GEODATENBANK-SCHEMA (PostGIS)
-- =============================================================================
-- Beschreibung: Speichert die aus OSM extrahierten Geometrien und verknüpft
--               sie performant mit den Matrix-Infospace-Containern.
-- =============================================================================

-- 1. PostGIS-Erweiterung aktivieren (falls noch nicht geschehen)
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Tabelle für die übergeordneten Infospaces (Container) anlegen
CREATE TABLE IF NOT EXISTS polaris_infospaces (
    id SERIAL PRIMARY KEY,
    matrix_space_id VARCHAR(255) NOT NULL UNIQUE, -- Die eindeutige Matrix-Raum-ID (!spaceID:domain.de)
    zone_name VARCHAR(255) NOT NULL,               -- Klartextname (z. B. "Goethe-Schule Goslar")
    osm_id BIGINT,                                 -- Optionale ID aus OpenStreetMap zur Rückverfolgung
    osm_tag_key VARCHAR(100),                      -- Welcher Tag hat gematcht? (z. B. "amenity")
    osm_tag_value VARCHAR(100),                    -- Welcher Wert? (z. B. "school")
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Geometrie-Spalte für die Polygone hinzufügen
-- Parameter: Tabelle, Spaltenname, SRID (4326 = WGS84 / GPS-Standard), Geometrietyp (POLYGON/MULTIPOLYGON), Dimension (2)
SELECT AddGeometryColumn('polaris_infospaces', 'geom', 4326, 'MULTIPOLYGON', 2);

-- 4. Strikten Geometrie-Constraint setzen (Verhindert korrupte GPS-Daten)
ALTER TABLE polaris_infospaces ADD CONSTRAINT enforce_valid_geometry CHECK (ST_IsValid(geom));

-- 5. Hochperformanten räumlichen GiST-Index anlegen
-- WICHTIG: Ohne diesen Index müsste PostGIS bei jedem einzelnen m.location-Event 
-- die komplette Tabelle sequentiell durchscannen. Der GiST-Index reduziert die 
-- Abfragezeit bei der ST_Contains-Prüfung auf wenige Millisekunden.
CREATE INDEX IF NOT EXISTS idx_polaris_infospaces_geom ON polaris_infospaces USING gist (geom);

-- 6. Trigger für automatische Zeitstempel-Aktualisierung (Optional, aber Best Practice)
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;   
END;
$$ language 'plpgsql';

CREATE TRIGGER update_polaris_infospaces_modtime
    BEFORE UPDATE ON polaris_infospaces
    FOR EACH ROW
    EXECUTE PROCEDURE update_modified_column();

-- =============================================================================
-- BEISPIEL-ABFRAGE FÜR DEN BOT-CODE (Zur Veranschaulichung)
-- =============================================================================
-- SELECT matrix_space_id 
-- FROM polaris_infospaces 
-- WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326));
