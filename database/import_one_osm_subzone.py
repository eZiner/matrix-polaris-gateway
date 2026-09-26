import os
import sys
import time                     
import requests
import psycopg2
from dotenv import load_dotenv

# Die unzerstörbaren API-Sicherheitsgurte gegen Timeouts & Drosselung [1.32]
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Holt deine funktionierende Multipolygon-Flächen-Synthese direkt mit rein
from sync_multipolygons import sync_missing_multipolygons
def create_robust_session():
    """Erstellt eine HTTP-Sitzung, die Timeouts und 429er-Drosselungen automatisch wiederholt."""
    session = requests.Session()
    retry_strategy = Retry(
        total=7,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"],  # 👑 KORREKTUR: Erlaubt automatische Retries bei POST! [1.32]
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# 1. SETUP & ENV-LADEN
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(os.path.dirname(project_root), 'services', 'matrix-gateway', '.env')
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
            FROM public.main_zones
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
        "out body geom qt;"
    )

    # --- DER UNZERSTÖRBARE API-SICHERHEITSGURT ---
    # Nutzt die robuste Session mit automatischem Exponential-Backoff bei Timeouts! [1.32]
    try:
        with create_robust_session() as session:
            res = session.post(OVERPASS_URL, data={'data': overpass_query}, headers=HEADERS, timeout=60)
        
        if res.status_code != 200:
            return "ERROR", f"OSM Overpass-API dauerhaft blockiert oder überlastet (Status {res.status_code})"
            
        data = res.json()
        
    except requests.exceptions.Timeout:
        return "ERROR", "Zeitüberschreitung (Timeout) bei der Overpass-API nach 60 Sekunden."
    except Exception as e:
        return "ERROR", f"Unerwarteter Netzwerkfehler beim API-Abruf: {str(e)}"
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
        
        # 1. GENERELLES FILTER: Ignoriere ALLE Objekte auf Ebene 8 (Hauptgemeinden) [1.21]
        # Das schmeißt sofort die "Großen Nachbarn" wie Goslar, Wernigerode etc. raus!
        sub_level = int(tags.get('admin_level', 9)) if el_type != 'node' else 11
        if sub_level == 8:
            continue

        if sub_name == mutter_name and el_type == 'relation':
            continue

        # Eindeutige, duplikatfreie ID basierend auf Typ und OSM-ID
        sub_ars = f"OSM_{el_type}_{osm_id}"

        # 👑 DIE RÄUMLICHE POSTGIS-SICHERHEITSBARRIERE FÜR ALLE TYPEN:
        # Wir ermitteln für jedes Objekt die exakte Koordinate (Node-Position oder Relations-Zentroid)
        if el_type == 'node':
            geom_data = el.get("geometry", {})
            lat = el.get("lat") or geom_data.get("lat")
            lon = el.get("lon") or geom_data.get("lon")
            sub_level = 11
        else:
            # Bei Relationen nutzen wir das von Overpass mitgelieferte Zentroid oder die erste Koordinate
            geom_data = el.get("bounds", el.get("center", {}))
            lat = el.get("center", {}).get("lat") or geom_data.get("minlat")
            lon = el.get("center", {}).get("lon") or geom_data.get("minlon")
            sub_level = int(tags.get('admin_level', 9))

        # Nur verarbeiten, wenn wir gültige Koordinaten für den Test haben
        if sub_name and lat and lon:
            # 🚀 DER UNBESTECHLICHE CHECK: Liegt der Punkt WIRKLICH in der echten Mutter-Gemarkung?
            # Das pulverisiert Grenzgänger und Nachbarorte sofort auf mathematischer Ebene!
            cur.execute("""
                SELECT ST_Contains(geometry, ST_SetSRID(ST_Point(%s, %s), 4326)) 
                FROM public.main_zones 
                WHERE ars_code = %s;
            """, (float(lon), float(lat), mutter_ars))
            
            is_inside = cur.fetchone()
            if is_inside and is_inside[0]:
                subzones_found.append({
                    "ars": str(sub_ars), "name": str(sub_name), "level": sub_level,
                    "type": el_type, "lat": float(lat), "lon": float(lon)
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
        # --- DIESEN BLOCK JETZT AUSKOMMENTIEREN ---
        # cur.execute("SELECT ars_code FROM public.sub_zones WHERE ars_code = %s;", (zone["ars"],))
        # exists = cur.fetchone()

        # if exists:
        #     if mode == 2:
        #         skipped_count += 1; continue
        #     elif mode == 3:
        #         cur.execute("DELETE FROM public.sub_zones WHERE ars_code = %s;", (zone["ars"],))
        #         overwritten_count += 1
        # ------------------------------------------

        try:
            if zone["type"] == "node":
                # Wir berechnen den Punkt und den Buffer vorab nativ in SQL, 
                # damit Psycopg2 keine Typen-Konflikte mit mutter_ars bekommt
                insert_query = """
                INSERT INTO public.sub_zones (ars_code, parent_ars, zone_name, admin_level, bundesland, landkreis, geometry)
                VALUES (
                    %s, %s, %s, %s, %s, %s, 
                    ST_Buffer(ST_SetSRID(ST_Point(%s, %s), 4326)::geography, 1500)::geometry
                )
                ON CONFLICT (ars_code) DO UPDATE 
                SET zone_name = EXCLUDED.zone_name,
                    geometry = EXCLUDED.geometry,
                    parent_ars = EXCLUDED.parent_ars;
                """
                # Expliziter Float-Cast für die Koordinaten beim Abschicken
                cur.execute(insert_query, (
                    str(zone["ars"]), 
                    str(mutter_ars).strip(), 
                    str(zone["name"]), 
                    int(zone["level"]), 
                    str(bl_code), 
                    str(lk_code), 
                    float(zone["lon"]), 
                    float(zone["lat"])
                ))
            else:
                insert_query = """
                INSERT INTO public.sub_zones (ars_code, parent_ars, zone_name, admin_level, bundesland, landkreis, geometry)
                VALUES (%s, %s, %s, %s, %s, %s, NULL)
                ON CONFLICT (ars_code) DO UPDATE
                SET zone_name = EXCLUDED.zone_name,
                    parent_ars = EXCLUDED.parent_ars;
                """
                cur.execute(insert_query, (zone["ars"], mutter_ars, zone["name"], zone["level"], bl_code, lk_code))
            inserted_count += 1
        except Exception as db_e:
            conn.rollback()
            cur.close(); conn.close()
            return "ERROR", f"Fehler beim Schreiben von '{zone['name']}': {db_e}"

    conn.commit()
    cur.close(); conn.close()

    # Vereinfachte, unzerstörbare Erfolgsmeldung
    summary = f"🎉 Erfolg für {mutter_name}: {inserted_count} Ortsteile im SLG-Rack synchronisiert."
    return "SUCCESS", summary


# 3. DAS HAUPTPROGRAMM
def main():
    # Lädt die Umgebungsvariablen für das SLG-Rack
    load_dotenv()
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if not DATABASE_URL:
        print("❌ FEHLER: DATABASE_URL nicht in der .env gefunden!")
        return

    # Verbindungsaufbau zur PostGIS
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        print("\n==========================================")
        print("      POLARIS AUTOMATED OSM-BATCH IMPORT   ")
        print("==========================================")
        print("1 = Einzelne Gemeinde importieren (Interaktiv)")
        print("2 = Ganzen Landkreis automatisch importieren (Sozialer Bot-Modus)")
        
        choice = input("\nDeine Auswahl: ").strip()
        
        if choice == "2":
            lk_name = input("Exakter Name des Landkreises (z.B. 'Goslar'): ").strip()
            mode_input = "3"  # Im Massenlauf erzwingen wir Modus 3 (Überschreiben)
            
            # Holt alle registrierten Gemeinden des Landkreises aus der BKG-Tabelle
            cur.execute("SELECT zone_name, ars_code FROM public.main_zones WHERE landkreis ILIKE %s;", (f"%{lk_name}%",))
            municipalities = cur.fetchall()
            
            if not municipalities:
                print(f"❌ Kein Landkreis mit dem Namen '{lk_name}' in main_zones gefunden!")
                return
                
            print(f"\n🚀 Starte Massen-Import für {len(municipalities)} Gemeinden im Landkreis {lk_name}...")
            
            for idx, (muni_name, ars_code) in enumerate(municipalities, 1):

                print(f"\n📦 [{idx}/{len(municipalities)}] Verarbeite {muni_name} (ARS: {ars_code})...")
                
                status, result = process_single_municipality(ars_code, int(mode_input))
                
                if status == "ERROR":
                    print(f"  ❌ Fehler bei {muni_name}: {result}")
                else:
                    print(f"  ✅ {result}")
                    print("  🔗 Starte Multipolygon-Flächen-Synthese...")
                    
                    # 👑 MINIMALER FIX: Wertet den Syncer-Ausstieg unbestechlich aus
                    sync_success = sync_missing_multipolygons()
                    if not sync_success:
                        print("\n👋 Massen-Import durch Syncer-Notbremse kontrolliert abgebrochen.")
                        break # Bricht die Gemeinde-Hauptschleife augenblicklich ab!

                if idx < len(municipalities):
                    print("⏳ Sozialer Bot-Modus: Warte 5 Sekunden vor der nächsten Gemeinde...")
                    time.sleep(5)

            print("\n🏁 AUTOMATISIERTER LANDKREIS-BATCH-IMPORT ERFOLGREICH BEENDET!")

        else:
            # --- DER INTERAKTIVE EINZEL-IMPORT-FALLBACK ---
            muni_input = input("\nGemeinde-Name oder ARS-Code: ").strip()
            mode_input = input("Modus (1=Show, 2=Import, 3=Overwrite): ").strip()
            
            status, result = process_single_municipality(muni_input, int(mode_input))
            if status == "ERROR":
                print(f"\n❌ FEHLER: {result}")
            elif status == "SUCCESS" or status == "DATA":
                print(f"\n{result}")
                
                # PostGIS-Fix: Syntaxfehler behoben und korrekte Liste eingesetzt
                if status == "SUCCESS" and int(mode_input) in [2, 3]:
                    print("\n🔗 Triggere automatischen Multipolygon-Sync für Flächengrenzen...")
                    try:
                        sync_missing_multipolygons()
                    except Exception as e:
                        print(f"⚠️ Sync fehlgeschlagen: {e}")

    except Exception as e:
        print(f"\n💥 Kritischer Fehler in der Hauptschleife: {e}")
    finally:
        # Ressourcen sauber freigeben
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
