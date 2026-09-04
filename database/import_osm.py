# import_osm.py (Speicherort: /database)
import os
import sys
import json
import requests
import psycopg2
from dotenv import load_dotenv

# 1. PFAD ERMITTELN (Aus /database rausgehen, in /production reingehen)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(project_root, 'production', '.env')

# 2. UMGEBUNGSVARIABLEN LADEN
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
KOMMUNE_NAME = os.getenv("KOMMUNE_NAME", "Goslar")

if not DATABASE_URL:
    print(f"❌ FEHLER: Die Umgebungsvariable 'DATABASE_URL' wurde nicht gefunden!", file=sys.stderr)
    print(f"Gesucht wurde an dieser Stelle: {env_path}", file=sys.stderr)
    sys.exit(1)

print(f"⏳ 1. Starte Live-Abfrage über Overpass API für Schulen in '{KOMMUNE_NAME}'...")

# 3. OVERPASS API-ABFRAGE (Deine funktionierende Version)
overpass_url = "https://overpass-api.de/api/interpreter" 

overpass_query = f"""[out:json][timeout:30];
area["boundary"="administrative"]["admin_level"="8"]["name"="{KOMMUNE_NAME}"]->.searchArea;
(
  way["amenity"="school"](area.searchArea);
  relation["amenity"="school"](area.searchArea);
);
out geom;"""

headers = {
    "User-Agent": "PolarisGatewayMunicipalImporter/1.0 (Contact: admin@polaris-project.de; Industrial Workspace Automation)",
    "Referer": "https://github.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json"
}

try:
    response = requests.post(overpass_url, data={'data': overpass_query}, headers=headers, timeout=45)
    response.raise_for_status()
    
    if not response.text.strip():
        print("❌ Fehler: Der Overpass-Server hat eine leere Antwort zurückgegeben.")
        sys.exit(1)
        
    try:
        res_data = response.json()
    except json.decoder.JSONDecodeError:
        print("❌ FEHLER: Der Server hat trotz korrekter Header kein gültiges JSON geantwortet!")
        print("--- SERVER ANTWORT START ---")
        print(response.text[:500])  
        print("--- SERVER ANTWORT ENDE ---")
        sys.exit(1)

except Exception as e:
    print(f"❌ Fehler bei der Netzwerk-Verbindung zu Overpass: {e}", file=sys.stderr)
    sys.exit(1)

elements = res_data.get('elements', [])
print(f"✅ 2. API-Daten empfangen. {len(elements)} Schulen (OSM-Elemente) gefunden.")

if not elements:
    print(f"⚠ Keine Schulen für die Region '{KOMMUNE_NAME}' in OpenStreetMap gefunden.")
    sys.exit(0)


print("🚀 3. Starte nativen Import in PostGIS...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    # Das fehleranfällige SET search_path wurde hier entfernt, da es beim Rollback gelöscht wird!
except Exception as db_e:
    print(f"❌ Fehler bei der Datenbankverbindung: {db_e}", file=sys.stderr)
    sys.exit(1)
    
inserted_count = 0

# 4. DATEN PARSEN UND IN POSTGIS EINTRAGEN
for el in elements:
    osm_id = el.get('id')
    tags = el.get('tags', {})
    zone_name = tags.get('name', f"Schule (OSM ID {osm_id})")
    
    geometry = el.get('geometry', [])
    
    if el.get('type') == 'relation':
        for member in el.get('members', []):
            if member.get('type') == 'way' and 'geometry' in member:
                geometry = member['geometry']
                break

    if not geometry or len(geometry) < 3:
        continue

    pt_strings = [f"{pt['lon']} {pt['lat']}" for pt in geometry]
    pt_strings.append(f"{geometry[0]['lon']} {geometry[0]['lat']}")
    
    wkt_points = ", ".join(pt_strings)
    wkt_geometry = f"MULTIPOLYGON((({wkt_points})))"

    try:
        # WICHTIG: Explizite Anführungszeichen um Schema und Tabelle fixieren den Pfad permanent!
        query_sql = """
            INSERT INTO polaris_infospaces (matrix_space_id, zone_name, osm_id, osm_tag_key, osm_tag_value, geom)
            VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
            ON CONFLICT (matrix_space_id) DO NOTHING;
        """
        fake_space_id = f"!goslar_school_{osm_id}:goslar.de"
        
        cur.execute(query_sql, (fake_space_id, zone_name, osm_id, 'amenity', 'school', wkt_geometry))
        inserted_count += cur.rowcount
    except Exception as sql_e:
        # Falls ein Eintrag fehlschlägt, verhindert das feste Schema oben, dass Postgres die Tabelle vergisst
        conn.rollback()
        print(f"⚠ Konnte Schule {osm_id} ({zone_name}) nicht importieren. Fehler: {sql_e}")
        continue

conn.commit()
cur.close()
conn.close()

print(f"🎉 POLARIS-Datenimport erfolgreich abgeschlossen! {inserted_count} Schulen wurden live via Overpass in PostGIS geladen.")
