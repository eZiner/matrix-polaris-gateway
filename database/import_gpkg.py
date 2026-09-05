# import_gpkg.py (KOMKOMBINIERTER BKG-INITIALISER - Speicherort: /database)
import os
import sys
import geopandas as gpd
from sqlalchemy import create_engine
import psycopg2
from dotenv import load_dotenv

# 1. SETUP & ENV-LADEN
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(project_root, 'production', '.env')
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ FEHLER: DATABASE_URL fehlt in der .env!", file=sys.stderr)
    sys.exit(1)

# 🔥 KORREKTUR: Dynamischer Pfad aus der .env statt hart codiertem G:\-Laufwerk!
GPKG_FILE = os.getenv("BKG_GPKG_PATH")
if not GPKG_FILE:
    print("❌ FEHLER: BKG_GPKG_PATH fehlt in der .env!", file=sys.stderr)
    sys.exit(1)

def main():
    if not os.path.exists(GPKG_FILE):
        print(f"❌ FEHLER: GeoPackage-Datei nicht gefunden unter Pfad:\n➔ {GPKG_FILE}")
        return

    # ➔ ABSCHNITT A: GEOMETRIE-TABELLE (polaris_infospaces) VORBEREITEN
    print("⏳ 1. Bereite PostGIS-Tabelle 'polaris_infospaces' vor...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
        # Erstellt die Tabelle mit der zukunftssicheren VARCHAR(50) Spalte
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.polaris_infospaces (
                ars_code VARCHAR(50) PRIMARY KEY,
                zone_name VARCHAR(255) NOT NULL,
                admin_level INT NOT NULL,
                bundesland VARCHAR(50) NOT NULL,
                landkreis VARCHAR(100) NOT NULL,
                matrix_space_id VARCHAR(255) UNIQUE,
                geometry geometry(MultiPolygon, 4326)
            );
        """)
        
        # 🔥 DIE RETTUNG FÜR DEN INITIAL-RUN: Leert die alten Testdaten restlos aus!
        # Das verhindert den "duplicate key"-Fehler beim erneuten BKG-Import.
        cur.execute("TRUNCATE TABLE public.polaris_infospaces CASCADE;")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Geometrie-Tabelle steht bereit und wurde für den Frischimport geleert.")
    except Exception as e:
        print(f"❌ DB-Fehler beim Geometrie-Setup: {e}")
        return

    # Engine für den schnellen Pandas-Bulk-Stream aufbauen
    engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql://"))

    # ➔ ABSCHNITT B: RELATIONALE NAMENSLISTEN IMPORTIEREN
    print("\n⏳ 2. Importiere relationale BKG-Namenslisten...")
    try:
        # ignore_geometry=True spart gewaltig RAM und Rechenzeit
        print("   ➔ Lade Bundesland-Namen (vg25_lan)...")
        df_lan = gpd.read_file(GPKG_FILE, layer="vg25_lan", ignore_geometry=True)
        df_lan[["ARS", "GEN"]].to_sql("bkg_lan_names", engine, if_exists="replace", index=False)
        print("   ✅ Tabelle 'bkg_lan_names' erfolgreich befüllt.")

        print("   ➔ Lade Landkreis-Namen (vg25_krs)...")
        df_krs = gpd.read_file(GPKG_FILE, layer="vg25_krs", ignore_geometry=True)
        df_krs[["ARS", "GEN"]].to_sql("bkg_krs_names", engine, if_exists="replace", index=False)
        print("   ✅ Tabelle 'bkg_krs_names' erfolgreich befüllt.")
    except Exception as e:
        print(f"❌ Fehler beim Import der Namenstabellen: {e}")
        return

    # ➔ ABSCHNITT C: DIE HOCHAUFLÖSENDEN BKG-GEMEINDEN STREAMEN
    print("\n⏳ 3. Lese hochauflösenden Gemeinde-Layer 'vg25_gem' ein...")
    try:
        gdf = gpd.read_file(GPKG_FILE, layer="vg25_gem")
    except Exception as e:
        print(f"❌ Fehler beim Einlesen des Gemeinde-Layers: {e}")
        return

    print(f"   ✅ {len(gdf)} BKG-Datensätze geladen. Projiziere live auf WGS84 (GPS)...")
    gdf = gdf.to_crs(epsg=4326)

    print("⏳ 4. Filter Großstädte (elastische POLARIS-Regel)...")
    if "EWZ" in gdf.columns:
        gdf = gdf[gdf["EWZ"] <= 100000]
        print(f"   ✅ Gefiltert auf {len(gdf)} Gemeinden unter 100k Einwohnern.")

    # Spalten für deine PostGIS-Tabelle mappen
    rename_dict = {
        "ARS": "ars_code",
        "GEN": "zone_name",
        "SN_L": "bundesland",
        "SN_K": "landkreis"
    }
    available_renames = {k: v for k, v in rename_dict.items() if k in gdf.columns}
    gdf = gdf.rename(columns=available_renames)

    # Hilfsspalten für POLARIS hinzufügen
    gdf["matrix_space_id"] = gdf["ars_code"].apply(lambda ars: f"!ars_{ars}:polaris-gateway.de")
    gdf["admin_level"] = 8

    # Nur die Spalten behalten, die exakt in unser Schema passen
    keep_cols = ["ars_code", "zone_name", "admin_level", "bundesland", "landkreis", "matrix_space_id", "geometry"]
    gdf = gdf[[c for c in keep_cols if c in gdf.columns]]

    print(f"\n⏳ 5. Streamen der Geometrien direkt in deine PostGIS-Datenbank...")
    try:
        # Falls die Tabelle leer ist oder du sie überschrieben hast, befüllt 'append' sie sauber neu
        gdf.to_postgis("polaris_infospaces", engine, if_exists="append", index=False)
        print("\n=====================================================================")
        print("🌐 INITIALISIERUNG ERFOLGREICH! BKG-BASISDATEN ENVIRONMENT-GELADEN!")
        print("=====================================================================")
        print("➔ Tabelle 'polaris_infospaces' (admin_level 8) ist bereit.")
        print("➔ Relationale Namenstabellen sind 100% dynamisch verknüpft.")
        print("=====================================================================")
    except Exception as e:
        print(f"❌ Fehler beim Datenbank-Upload der Geometrien: {e}")

if __name__ == "__main__":
    main()
