# import_one_osm_subzone.py (URGESTEIN-EDITION MIT POLYGON + NODE-BUFFER - Speicherort: /database)
import os
import sys
import requests
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

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HEADERS = {
    "User-Agent": "PolarisGatewayMunicipalImporter/1.0 (Contact: admin@polaris-project.de; Industrial Workspace Automation)",
    "Referer": "https://github.com",
    "Content-Type": "application/x-www-form-urlencoded"
}

# 2. DIE KERN-FUNKTION
def process_single_municipality(muni_input, mode):
    """
    Verarbeitet eine einzelne Gemeinde basierend auf ARS oder Name.
    Holt administrative Grenzen UND reine Ortsteil-Punkte (wie Buntenbock) aus OSM!
    """
    if mode == 4:
        return "SUCCESS", "Programm beendet."

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
    except Exception as e:
        return "ERROR", f"Datenbank-Verbindungsfehler: {e}"

    # Schritt A: Ermittle den echten Mutter-ARS und extrahiere das vereinfachte Polygon aus PostGIS
    muni_input_str = str(muni_input).strip()
    
    sql_base = """
        SELECT ars_code, zone_name,
               string_agg(ST_Y(geom.geom) || ' ' || ST_X(geom.geom), ' ') as poly_points
        FROM (
            SELECT ars_code, zone_name, (ST_DumpPoints(ST_Simplify(geometry, 0.001))).* 
            FROM public.polaris_infospaces 
            WHERE admin_level = 8
    """
    
    if muni_input_str.isdigit():
        cur.execute(sql_base + " AND ars_code LIKE %s || '%%') as geom GROUP BY ars_code, zone_name LIMIT 1;", (muni_input_str,))
    else:
        cur.execute(sql_base + " AND LOWER(zone_name) = LOWER(%s)) as geom GROUP BY ars_code, zone_name LIMIT 1;", (muni_input_str,))
        
    db_row = cur.fetchone()
    if not db_row or not db_row[2]:
        cur.close(); conn.close()
        return "ERROR", f"Gemeinde '{muni_input}' nicht gefunden oder keine Geometrie in PostGIS!"

    mutter_ars, mutter_name, poly_points = db_row
    poly_points_clean = " ".join(poly_points.split())

    # Schritt B: Erweiterte Overpass-Query!
    # Holt Relationen (Ebene 8,9,10) UND Punkte (village/hamlet) exakt innerhalb der Gemarkung!
    overpass_query = (
        "[out:json][timeout:45];"
        "("
        f'relation["boundary"="administrative"]["admin_level"~"8|9|10"](poly:"{poly_points_clean}");'
        f'node["place"~"village|hamlet|suburb"](poly:"{poly_points_clean}");'
        ");"
        "out tags qt;"
    )

    try:
        res = requests.post(OVERPASS_URL, data={'data': overpass_query}, headers=HEADERS, timeout=60)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        cur.close(); conn.close()
        return "ERROR", f"OSM Overpass-API Fehler: {e}"
    
    elements = data.get('elements', [])
    if not elements:
        cur.close(); conn.close()
        return "DATA", []

    subzones_found = []
    for el in elements:
        tags = el.get('tags', {})
        sub_name = tags.get('name')
        el_type = el.get('type')
        osm_id = el.get('id')
        
        # Ignoriere die Muttergemeinde selbst, falls sie in der Liste auftaucht
        if sub_name == mutter_name and el_type == 'relation':
            continue

        sub_ars = tags.get('de:regionalschluessel') or tags.get('de:amtlicher_gemeindeschluessel')
        if not sub_ars:
            sub_ars = f"{str(mutter_ars)[:9]}_{osm_id}"

        if el_type == 'node':
            # Reine Punkte markieren wir als künstliches Level 11 für unsere Puffer-Logik
            sub_level = 11
            # Buntenbock-Fix: Wenn ein Ortsteil-Knoten den gleichen Namen wie ein bekannter Ort hat, zulassen
            if sub_name:
                subzones_found.append({
                    "ars": str(sub_ars), "name": str(sub_name), "level": sub_level,
                    "type": "node", "lat": el.get("lat"), "lon": el.get("lon")
                })
        else:
            sub_level = int(tags.get('admin_level', 9))
            if sub_name and sub_level in [8,9]:
                subzones_found.append({
                    "ars": str(sub_ars), "name": str(sub_name), "level": sub_level,
                    "type": "relation", "lat": None, "lon": None
                })

    if mode == 1:
        cur.close(); conn.close()
        return "DATA", subzones_found

    # Modus 2 & 3: Datenbank-Schreibvorgänge
    inserted_count = 0
    skipped_count = 0
    overwritten_count = 0

    bl_code = str(mutter_ars)[:2]
    lk_code = str(mutter_ars)[:5]

    for zone in subzones_found:
        cur.execute("SELECT ars_code FROM public.polaris_infospaces WHERE ars_code = %s;", (zone["ars"],))
        exists = cur.fetchone()

        if exists:
            if mode == 2:
                skipped_count += 1; continue
            elif mode == 3:
                cur.execute("DELETE FROM public.polaris_infospaces WHERE ars_code = %s;", (zone["ars"],))
                overwritten_count += 1

        try:
            if zone["type"] == "node":
                # Der magische PostGIS-Puffer: Erzeugt ein echtes 1500m-Polygon um den GPS-Punkt (Buntenbock)!
                cur.execute("""
                    INSERT INTO public.polaris_infospaces (ars_code, zone_name, admin_level, bundesland, landkreis, matrix_space_id, geometry)
                    VALUES (%s, %s, %s, %s, %s, %s, ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 1500)::geometry);
                """, (zone["ars"], zone["name"], zone["level"], bl_code, lk_code, f"!ars_{zone['ars']}:polaris-gateway.de", zone["lon"], zone["lat"]))
            else:
                # Für echte Relationen ziehen wir die Geometrie später über den großen Bruder nach
                cur.execute("""
                    INSERT INTO public.polaris_infospaces (ars_code, zone_name, admin_level, bundesland, landkreis, matrix_space_id, geometry)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL);
                """, (zone["ars"], zone["name"], zone["level"], bl_code, lk_code, f"!ars_{zone['ars']}:polaris-gateway.de"))
            inserted_count += 1
        except Exception as db_e:
            conn.rollback()
            cur.close(); conn.close()
            return "ERROR", f"Fehler beim Schreiben von '{zone['name']}': {db_e}"

    conn.commit()
    cur.close(); conn.close()

    summary = f"🎉 Erfolg für {mutter_name}: {inserted_count} importiert"
    if skipped_count > 0: summary += f", {skipped_count} übersprungen"
    if overwritten_count > 0: summary += f", {overwritten_count} aktualisiert"
    return "SUCCESS", summary


# 3. DAS HAUPTPROGRAMM
def main():
    while True:
        print("\n==================================================")
        print("      POLARIS SUBZONEN ERGÄNZUNGS-IMPORT          ")
        print("==================================================")
        muni_input = input("Gib den NAMEN oder den ARS der Gemeinde ein: ").strip()
        if not muni_input:
            continue

        print("\n--- STEUERUNGS-MODUS ---")
        print("1 = Gefundene Sub-Zonen nur ANZEIGEN (Kein Import)")
        print("2 = Sub-Zonen IMPORTIEREN (Nur wenn noch nicht vorhanden)")
        print("3 = Sub-Zonen IMPORTIEREN & ÜBERSCHREIBEN (Falls vorhanden)")
        print("4 = Programm beenden")
        
        mode_input = input("\nWähle einen Modus (1-4): ").strip()
        if mode_input == '4':
            print("👋 Programm beendet. Bis zum nächsten Mal!")
            break
            
        if mode_input not in ['1', '2', '3']:
            print("❌ Ungültige Modus-Auswahl!")
            continue

        status, result = process_single_municipality(muni_input, int(mode_input))

        if status == "ERROR":
            print(f"\n❌ FEHLER: {result}")
        elif status == "DATA":
            if not result:
                print(f"\nℹ️  Es wurden keine feineren Sub-Zonen in OSM für '{muni_input}' innerhalb des Polygons gefunden.")
            else:
                print(f"\n📋 Gefundene Sub-Zonen in OpenStreetMap ({len(result)} Einträge):")
                print(f"{'ARS-Code':<14} | {'Ortsteil-Name':<30} | {'OSM-Level'}")
                print("-" * 60)
                for zone in result:
                    lvl_str = f"admin_level={zone['level']}" if zone['level'] != 11 else "PLACE_NODE (Buffered)"
                    print(f"{zone['ars']:<14} | {zone['name']:<30} | {lvl_str}")
        elif status == "SUCCESS":
            print(f"\n{result}")

if __name__ == "__main__":
    main()
