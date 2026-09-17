import os
import sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# 1. Setup & .env aus dem 'production'-Ordner laden
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(project_root, 'production', '.env')
load_dotenv(dotenv_path=env_path)

try:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    # Wir nutzen hier den Standard-Cursor und greifen über Indizes zu,
    # um jegliche Dict- und Attribut-Fehler unter Windows/WSL zu eliminieren!
    cur = conn.cursor()
except Exception as e:
    print(f"❌ DB-Fehler: {e}")
    sys.exit(1)

print("="*60)
print(" 🛰️ POLARIS CORE GEOFENCING PRÜFSTAND")
print("="*60)

# Eingabe-Schleife
while True:
    lon = input("\n📍 Longitude (X, z.B. 10.33472 für Buntenbock): ").strip()
    if lon.lower() == 'q': break
    lat = input("📍 Latitude  (Y, z.B. 51.80434 für Buntenbock): ").strip()
    
    try:
        lon, lat = float(lon), float(lat)
        
        # STUFE 1: Hauptgemeinde ermitteln (Reines SQL)
        cur.execute("""
            SELECT ars_code, zone_name 
            FROM public.main_zones 
            WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """, (lon, lat))
        main_zone = cur.fetchone()
        
        if not main_zone:
            print("⚪ Punkt liegt außerhalb aller Gemeinden.")
            continue
            
        mutter_ars = str(main_zone[0]).strip()
        mutter_name = str(main_zone[1]).strip()
        print(f"🟢 HAUPTZONE: {mutter_name} (ARS: {mutter_ars})")
        
        # STUFE 2: Sub-Zonen völlig unbeschwert von ARS-Filtern suchen!
        # Wenn der Punkt im Polygon/Kreis liegt, MUSS PostGIS ihn ausspucken!
        cur.execute("""
            SELECT zone_name, admin_level 
            FROM public.sub_zones 
            WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """, (lon, lat))
        sub_zones = cur.fetchall()
        
        print(f"🏡 SUB-ZONEN ({len(sub_zones)} Treffer):")
        for row in sub_zones:
            lvl = "PLACE_NODE (1500m Buffer)" if row[1] == 11 else f"admin_level={row[1]}"
            print(f"  ► {row[0]:<25} | Typ: {lvl}")
            
    except ValueError:
        print("❌ Ungültige Zahlen!")
    except Exception as e:
        print(f"❌ Fehler: {e}")
