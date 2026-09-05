-- POLARIS GATEWAY - VOLLSTÄNDIGES DATENBANKSCHEMA
-- Zeitstempel: Samstag, 5. September 2026
-- Ziel-Plattform: PostgreSQL mit PostGIS-Erweiterung

-- ---------------------------------------------------------------------------
-- 1. ERWEITERUNGEN AKTIVIEREN
-- ---------------------------------------------------------------------------
-- PostGIS aktivieren, falls noch nicht geschehen (erfordert Superuser-Rechte)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- 2. RELATIONALE NAMENS-NACHSCHLAGETABELLEN (BKG-KLARNAME-MAPPINGS)
-- ---------------------------------------------------------------------------
-- Hinweis: Diese Tabellen werden von import_gpkg.py via pandas.to_sql befüllt
-- und vom cli_manager.py für den dynamischen Drilldown genutzt.

CREATE TABLE IF NOT EXISTS public.bkg_lan_names (
    "ARS" VARCHAR(2) PRIMARY KEY,
    "GEN" VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.bkg_krs_names (
    "ARS" VARCHAR(5) PRIMARY KEY,
    "GEN" VARCHAR(255) NOT NULL
);

-- ---------------------------------------------------------------------------
-- 3. HAUPTTABELLE FÜR GEOMETRIEN UND MATRIX-SPACES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.polaris_infospaces (
    -- KORREKTUR: VARCHAR(50) erlaubt die längeren OSM-Kombi-IDs (z.B. MutterARS_OSMID)
    ars_code VARCHAR(50) PRIMARY KEY,
    zone_name VARCHAR(255) NOT NULL,
    admin_level INT NOT NULL, -- 8 = BKG Gemeinde, 9/10 = OSM Ortsteil, 11 = OSM Node (Buffered)
    bundesland VARCHAR(50) NOT NULL, -- 2-stelliger BKG-Ländercode (z.B. 03)
    landkreis VARCHAR(100) NOT NULL, -- 5-stelliger BKG-Kreiscode (z.B. 03153)
    matrix_space_id VARCHAR(255) UNIQUE, -- Eindeutige Matrix-Raum-Adresse
    geometry geometry(Geometry, 4326) -- Nimmt MultiPolygone (BKG) und buffered Polygone (OSM) auf
);

-- ---------------------------------------------------------------------------
-- 4. PERFORMANCE-INDIZES FÜR HYPERLOKALES Echtzeit-GEOFENCING
-- ---------------------------------------------------------------------------
-- Räumlicher GIST-Index für die blitzschnelle ST_Contains Abfrage im Rust-Gateway
CREATE INDEX IF NOT EXISTS idx_polaris_geometry 
ON public.polaris_infospaces USING gist (geometry);

-- B-Tree Indizes für den schnellen relationalen Drilldown im CLI-Manager
CREATE INDEX IF NOT EXISTS idx_polaris_ars_prefix 
ON public.polaris_infospaces (ars_code);

CREATE INDEX IF NOT EXISTS idx_polaris_bundesland_landkreis 
ON public.polaris_infospaces (bundesland, landkreis);
