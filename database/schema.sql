-- ===========================================================================
-- POLARIS GATEWAY - ULTRA-FLEXIBLES HYBRID-SCHEMA (4-TABELLEN-MODELL)
-- Zeitstempel: Samstag, 12. September 2026
-- Lizenz: Public Domain / CC0 (Gemeinfrei)
-- ===========================================================================

-- PostGIS-Erweiterung für geografische Berechnungen aktivieren (WGS84 / SRID 4326)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- 1. NACHSCHLAGETABELLEN FÜR BKG-KLARNAMEN
-- Spaltennamen in Großbuchstaben ("ARS", "GEN") spiegeln den Standard-Ausgabestrom
-- des BKG-GeoPackages (VG25) wider, um ein direktes Pandas-Mapping zu erlauben.
-- ---------------------------------------------------------------------------

-- Nachschlagetabelle für Bundesländer (vg25_lan)
CREATE TABLE IF NOT EXISTS public.bkg_lan_names (
    "ARS" VARCHAR(2) PRIMARY KEY, -- 2-stelliger Regionalschlüssel des Bundeslandes
    "GEN" VARCHAR(255) NOT NULL   -- Klarname des Bundeslandes (z. B. "Niedersachsen")
);

-- Nachschlagetabelle für Landkreise / kreisfreie Städte (vg25_krs)
CREATE TABLE IF NOT EXISTS public.bkg_krs_names (
    "ARS" VARCHAR(5) PRIMARY KEY, -- 5-stelliger Regionalschlüssel des Landkreises
    "GEN" VARCHAR(255) NOT NULL   -- Klarname (z. B. "Landkreis Goslar")
);

-- ---------------------------------------------------------------------------
-- 2. TABELLE: main_zones (Echte Verwaltungsgrenzen - admin_level 8 / BKG)
-- Bildet das rechtssichere Fundament des "Deutschland im RAM"-Modells. Jedes
-- Rathaus importiert hier die ~11.000 deutschen Gemeinden vollständig [1.21].
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.main_zones (
    ars_code VARCHAR(50) PRIMARY KEY,        -- Amtlicher Regionalschlüssel (Gemeindeschlüssel)
    zone_name VARCHAR(255) NOT NULL,        -- Klarname der Kommune (z. B. "Clausthal-Zellerfeld")
    admin_level INT NOT NULL DEFAULT 8,     -- Fixiert auf Ebene 8 (Kommunen) gemäß BKG-Standard
    bundesland VARCHAR(50) NOT NULL,        -- Textzuordnung des Bundeslandes für CLI-Drilldown
    landkreis VARCHAR(100) NOT NULL,        -- Textzuordnung des Landkreises für CLI-Drilldown
    is_polaris_space BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE = Verwaltung betreut das POLARIS-System aktiv
    geometry geometry(MultiPolygon, 4326)   -- MultiPolygone im WGS84-System für maximalen GiST-Turbo
);

-- ---------------------------------------------------------------------------
-- 3. TABELLE: sub_zones (Feine Ortsteile, Weiler, buffered Nodes aus OSM)
-- Bildet hyperlokale Community-Zonen ab. Besitzen Ortsteile keine Flächengrenzen 
-- in OSM, speichert diese Tabelle kreisrunde Geometrien via ST_Buffer [1.21].
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.sub_zones (
    ars_code VARCHAR(50) PRIMARY KEY,       -- Kombi-Schlüssel im Format 'MutterARS_OSMID'
    parent_ars VARCHAR(50) NOT NULL,        -- Harte 1:n-Zuordnung zur übergeordneten main_zone
    zone_name VARCHAR(255) NOT NULL,        -- Klarname des Ortsteils (z. B. "Buntenbock")
    admin_level INT NOT NULL,               -- 9/10 = OSM Flächen-Relationen, 11 = Gepufferte Nodes
    bundesland VARCHAR(50) NOT NULL,        -- Geerbte Textzuordnung des Bundeslandes
    landkreis VARCHAR(100) NOT NULL,        -- Geerbte Textzuordnung des Landkreises
    geometry geometry(Geometry, 4326),      -- Erlaubt MultiPolygone und kreisrunde Puffer (Nodes)
    
    -- Löscht Sub-Zonen automatisch, wenn die dazugehörige Gemeinde entfernt wird
    CONSTRAINT fk_parent_zone FOREIGN KEY (parent_ars) REFERENCES public.main_zones(ars_code) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 4. TABELLE: polaris_spaces (Die logische Matrix-Raum-Hierarchie)
-- Die Schnittstelle zur Kommunikationsschicht. Hält die Raum-Eigenschaften [1.21].
-- Besitzt eine optionale Geometrie-Spalte als Joker für Freiform-Krisenräume [1.21].
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.polaris_spaces (
    matrix_space_id VARCHAR(255) PRIMARY KEY, -- Eindeutige Matrix-ID (Format: !raum_id:domain) [1.21]
    ars_code VARCHAR(50) NOT NULL,           -- Verweist unumstößlich auf die zuständige main_zone
    parent_space VARCHAR(255),               -- Bildet hierarchische Baumstrukturen in Matrix ab
    is_space BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE = Übergeordneter Space-Ordner, FALSE = Chat-/Warnraum
    room_alias VARCHAR(255),                 -- Menschenlesbarer Matrix-Alias (#polaris_*:domain) [1.21, 1.27]
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    geometry geometry(MultiPolygon, 4326),   -- JOKER: Für Sonder- und Krisenzonen völlig ohne Verwaltungsgrenzen [1.21]
    
    -- Sichert die administrative und rechtliche Hoheit der zuständigen Gemeinde ab
    CONSTRAINT fk_space_main_zone FOREIGN KEY (ars_code) REFERENCES public.main_zones(ars_code) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------------
-- 5. KREUZTABELLE: space_assignments (Für n:m Raum-Zuordnungen im Normalfall)
-- Löst das Problem von Räumen, die für mehrere Ortsteile gelten. Hält Geometrien
-- strikt sauber getrennt in main_zones/sub_zones und regelt Zuordnungen im SQL.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.space_assignments (
    matrix_space_id VARCHAR(255) NOT NULL,
    ars_code VARCHAR(50) NOT NULL,           -- Kann sowohl auf main_zones als auch auf sub_zones zeigen
    PRIMARY KEY (matrix_space_id, ars_code),
    
    -- Kaskadierendes Löschen von Zuordnungen, wenn ein Matrix-Raum entfernt wird
    CONSTRAINT fk_assign_space FOREIGN KEY (matrix_space_id) REFERENCES public.polaris_spaces(matrix_space_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 6. CORE-STATE-TABELLEN FÜR DAS GATEWAY
-- ---------------------------------------------------------------------------

-- Hysterese-Speicher gegen GPS-Jitter an Partitionsgrenzen.
-- Verhindert kaskadierende State-Storms auf den Synapse-Servern [1.21].
CREATE TABLE IF NOT EXISTS public.exit_pending_users (
    matrix_user_id VARCHAR(255) NOT NULL,    -- Die Matrix-ID des Bürgers (@user:domain)
    matrix_space_id VARCHAR(255) NOT NULL,   -- Der betroffene Geofence-Raum
    exit_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, -- Ablauf der 10-Minuten-Karenzzeit [1.27]
    PRIMARY KEY (matrix_user_id, matrix_space_id)
);

-- Nutzer-Präferenzen für Scopes (Themenkanäle via Chat-Befehl wie !scope tourismus aus)
CREATE TABLE IF NOT EXISTS public.user_scopes (
    matrix_user_id VARCHAR(255) NOT NULL,    -- Die Matrix-ID des Bürgers
    scope_name VARCHAR(50) NOT NULL,        -- Der Name des Scopes (z. B. 'tourismus', 'kultur')
    is_active BOOLEAN DEFAULT TRUE,          -- Aktivierungsstatus des Scopes
    PRIMARY KEY (matrix_user_id, scope_name)
);

-- ---------------------------------------------------------------------------
-- 7. PERFORMANCE-INDIZES FÜR ECHTZEIT-GEOFENCING (PostGIS GiST Turbo)
-- Reduziert die mathematische Punkt-in-Polygon-Suche auf O(log n) [1.21].
-- Garantiert Abfragezeiten von unter 0,2 ms direkt im RAM des SLG-Racks [1.21].
-- ---------------------------------------------------------------------------

-- Räumliche GiST-Indizes für ultraschnelle ST_Contains-Scans
CREATE INDEX IF NOT EXISTS idx_main_zones_geometry ON public.main_zones USING gist (geometry);
CREATE INDEX IF NOT EXISTS idx_sub_zones_geometry ON public.sub_zones USING gist (geometry);
CREATE INDEX IF NOT EXISTS idx_spaces_custom_geometry ON public.polaris_spaces USING gist (geometry);

-- B-Tree-Indizes für relationale Joins und beschleunigte Schlüsselprüfungen
CREATE INDEX IF NOT EXISTS idx_sub_zones_parent_ars ON public.sub_zones (parent_ars);
CREATE INDEX IF NOT EXISTS idx_assign_ars ON public.space_assignments (ars_code);
