# cli_manager.py (100% ARS-BASIERTER DRILLDOWN - Speicherort: /database)
import os
import sys
import psycopg2
import psycopg2.extras  # <-- DIESE ZEILE HINZUFÜGEN!
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(script_dir), 'production', '.env')
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ FEHLER: DATABASE_URL fehlt in der .env!", file=sys.stderr); sys.exit(1)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def select_bundesland(cur):
    """Schritt 1: Schneidet das BL live aus dem ARS und verknüpft den Namen."""
    cur.execute("""
        SELECT DISTINCT SUBSTR(ars_code, 1, 2) as bl_code, n."GEN"
        FROM public.main_zones i
        JOIN public.bkg_lan_names n ON SUBSTR(i.ars_code, 1, 2) = n."ARS"
        ORDER BY n."GEN" ASC;
    """)
    laender = cur.fetchall()
    if not laender:
        print("⚠ Keine Daten gefunden. Hast du import_gpkg.py und import_names.py ausgeführt?")
        return None

    while True:
        print("\n=== STEP 1: BUNDESLAND AUSWAHL ===")
        for idx, (code, name) in enumerate(laender, 1):
            print(f"{idx:>2} = {name} (Code: {code})")
        print(" E = Beenden")
        
        choice = input("\nWähle ein Bundesland: ").strip()
        if choice.lower() == 'e': return None
        if choice.isdigit() and 0 < int(choice) <= len(laender):
            return laender[int(choice) - 1]
        print("❌ Ungültige Auswahl.")

def select_landkreis(cur, bl_code, bl_name):
    """Schritt 2: Schneidet den Landkreis (Stelle 1-5) live aus dem ARS."""
    if bl_name in ["Berlin", "Hamburg", "Bremen"]:
        return bl_code, bl_name

    cur.execute("""
        SELECT DISTINCT SUBSTR(i.ars_code, 1, 5) as krs_code, n."GEN"
        FROM public.main_zones i
        JOIN public.bkg_krs_names n ON SUBSTR(i.ars_code, 1, 5) = n."ARS"
        WHERE SUBSTR(i.ars_code, 1, 2) = %s
        ORDER BY n."GEN" ASC;
    """, (bl_code,))
    kreise = cur.fetchall()

    if not kreise:
        print(f"⚠️  Keine Landkreise für {bl_name} über den ARS-Match gefunden.")
        return None

    while True:
        print(f"\n=== STEP 2: LANDKREISE IN {bl_name.upper()} ===")
        for idx, (code, name) in enumerate(kreise, 1):
            print(f"{idx:>3} = {name} (Code: {code})")
        print("  Z = Zurück zur Bundesland-Auswahl")
        
        choice = input("\nWähle einen Landkreis: ").strip()
        if choice.lower() == 'z': return "BACK"
        if choice.isdigit() and 0 < int(choice) <= len(kreise):
            return kreise[int(choice) - 1]
        print("❌ Ungültige Auswahl.")

def select_gemeinde(cur, bl_code, lk_code, lk_name):
    """Schritt 3: Holt alle Gemeinden, die mit dem Landkreis-Präfix beginnen."""
    if bl_code in ["11", "02", "04"]: # Stadtstaaten
        cur.execute("""
            SELECT ars_code, zone_name
            FROM public.main_zones
            WHERE SUBSTR(ars_code, 1, 2) = %s ORDER BY zone_name ASC;
        """, (bl_code,))
    else:
        cur.execute("""
            SELECT ars_code, zone_name
            FROM public.main_zones
            WHERE SUBSTR(ars_code, 1, 5) = %s ORDER BY zone_name ASC;
        """, (lk_code,))
        
    gemeinden = cur.fetchall()
    if not gemeinden:
        print(f"⚠ Keine Gemeinden für {lk_name} gefunden.")
        return None

    while True:
        print(f"\n=== STEP 3: GEMEINDEN IN {lk_name.upper()} ===")
        for idx, (ars, name) in enumerate(gemeinden, 1):
            print(f"{idx:>3} = {name} (ARS: {ars})")
        print("  Z = Zurück zur Landkreis-Auswahl")
        
        choice = input("\nWähle eine Gemeinde für den Polygon-Drilldown: ").strip()
        if choice.lower() == 'z': return "BACK"
        if choice.isdigit() and 0 < int(choice) <= len(gemeinden):
            return gemeinden[int(choice) - 1]
        print("❌ Ungültige Auswahl.")

def show_polygon_wkt(cur, ars_code, zone_name):
    """Schritt 4: Holt das Hauptpolygon und listet alle importierten Sub-Zonen auf."""
    print(f"\n ⏳ Lese hochauflösendes VG25-Polygon für '{zone_name}'...")
    cur.execute("SELECT ST_AsText(geometry) FROM public.main_zones WHERE ars_code = %s;", (ars_code,))
    row = cur.fetchone()
    wkt_text = row[0] if row and row[0] else "Keine Haupt-Geometrie hinterlegt!"

    # NEU: Integrierter Drilldown zu den zugehörigen Ortsteilen aus den sub_zones [1.21]
    cur.execute("""
        SELECT zone_name, admin_level 
        FROM public.sub_zones 
        WHERE parent_ars = %s 
        ORDER BY admin_level ASC, zone_name ASC;
    """, (ars_code,))
    sub_zones = cur.fetchall()

    print("\n" + "="* 70 + f"\n 🌐 POSTGIS WKT-POLYGON FÜR: {zone_name.upper()}\n" + "="* 70)
    print(f"{wkt_text[:300]} ... [Gekürzt! Gesamtzeichen: {len(wkt_text)}]")
    print("="* 70)

    print(f"\n 🏡 IMPORTIERTE SUB-ZONEN / ORTSTEILE ({len(sub_zones)} Einträge):")
    print("-" * 70)
    if sub_zones:
        for name, level in sub_zones:
            lvl_desc = "PLACE_NODE (1500m Puffer)" if level == 11 else f"admin_level={level}"
            print(f" • {name:<35} | Typ/Ebene: {lvl_desc}")
    else:
        print(" ⚪ Noch keine Sub-Zonen für diese Gemeinde über OSM importiert.")
    print("="* 70)
    
    input("\n[Drücke ENTER für das Hauptmenü]")

def test_gps_geofencing(cur):
    """Nimmt GPS-Koordinaten entgegen und feuert die PostGIS-ST_Contains-Kaskade ab."""
    print("\n" + "="*50 + "\n 🛰️ POLARIS LIVE-GEOFENCING SIMULATOR\n" + "="*50)
    try:
        lon_input = input(" 📍 Längengrad (Longitude / X, z.B. 10.33472): ").strip()
        lat_input = input(" 📍 Breitengrad (Latitude / Y,  z.B. 51.80434): ").strip()
        
        if not lon_input or not lat_input:
            return

        lon, lat = float(lon_input), float(lat_input)
        
        # 1. Stufe: Abfrage der BKG-Hauptgemeinde [1.21]
        cur.execute("""
            SELECT ars_code, zone_name, landkreis, bundesland 
            FROM public.main_zones 
            WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """, (lon, lat))
        main_zone = cur.fetchone()
        
        if not main_zone:
            print("\n ⚪ Koordinaten liegen in keiner POLARIS-Gemeinde (Außerhalb des ländlichen Meshs).")
            input("\n[ENTER drücken]")
            return

        print(f"\n 🟢 TREFFER IN HAUPTZONE (Ebene 8):")
        print(f"   • Gemeinde:  {main_zone['zone_name']} (ARS: {main_zone['ars_code']})")
        print(f"   • Region:    {main_zone['landkreis']}, {main_zone['bundesland']}")

        # 2. Stufe: Abfrage der hyperlokalen OSM-Subzonen
        # Nutzt LIKE und schneidet das Prefix ab, um 9- und 12-stellige BKG/OSM-Keys zu vereinen!
        cur.execute("""
            SELECT zone_name, admin_level 
            FROM public.sub_zones 
            WHERE (parent_ars = %s OR %s LIKE parent_ars || '%%')
              AND ST_Contains(geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            ORDER BY admin_level ASC;
        """, (main_zone['ars_code'], main_zone['ars_code'], lon, lat))
        sub_zones = cur.fetchall()

        print(f"\n 🏡 AKTIVE HYPERLOKALE GEOMETRIEN ({len(sub_zones)} Treffer):")
        print("-" * 50)
        if sub_zones:
            for name, level in sub_zones:
                lvl_desc = "PLACE_NODE (1500m Puffer)" if level == 11 else f"admin_level={level}"
                print(f"   ► {name:<25} | Typ: {lvl_desc}")
        else:
            print("   ⚪ Keine spezifische Sub-Zone an diesem Punkt aktiv.")
            
    except ValueError:
        print(" ❌ Fehler: Ungültiges Koordinaten-Format! Bitte Dezimalzahlen nutzen (z.B. 10.33).")
    
    print("="*50)
    input("\n[ENTER für Hauptmenü]")

def main_loop():
    conn = get_db_connection(); cur = conn.cursor()
    while True:
        print("\n==========================================")
        print("   POLARIS RELATIONAL DRILLDOWN (VG25)   ")
        print("==========================================")
        print("1 = Lokalen Zonen-Drilldown starten")
        print("2 = Zonen anhand GPS-Koordinaten finden")
        print("E = Beenden")
        action = input("\nDeine Auswahl: ").strip().lower()
        if action == 'e': break
        elif action == '1':
            while True:
                bl_info = select_bundesland(cur)
                if not bl_info: break
                bl_code, bl_name = bl_info
                
                lk_info = select_landkreis(cur, bl_code, bl_name)
                if lk_info == "BACK": continue
                if not lk_info: break
                lk_code, lk_name = lk_info
                
                gem_info = select_gemeinde(cur, bl_code, lk_code, lk_name)
                if gem_info == "BACK": continue
                if not gem_info: break
                gem_ars, gem_name = gem_info
                
                show_polygon_wkt(cur, gem_ars, gem_name)
                break
        elif action == '2':
            # Erzwingt den DictCursor temporär für diese Funktion
            with cur.connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as dict_cur:
                test_gps_geofencing(dict_cur)
    cur.close(); conn.close()

if __name__ == "__main__":
    main_loop()
