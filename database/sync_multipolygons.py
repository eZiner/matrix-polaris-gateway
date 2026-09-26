#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLARIS INFRASTRUCTURE PIPELINE - MULTIPOLYGON SYNCER
Zieht die echten OSM-Flächengrenzen für die Relationen in sub_zones [1.21].
Zeitstempel: Sonntag, 13. September 2026
Lizenz: Public Domain / CC0 (Gemeinfrei)
"""

import os
import sys
import json
import time
import requests
import psycopg2
from dotenv import load_dotenv


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
    "User-Agent": "PolarisGatewayPolygonSyncer/1.0 (Contact: admin@polaris-project.de)",
    "Referer": "https://github.com"
}
def sync_missing_multipolygons():
    """Holt die echten Grenzpolygone für Relationen aus OSM und schließt die NULL-Lücken [1.21]."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
    except Exception as e:
        print(f"❌ DB-Verbindungsfehler: {e}")
        return

    # Suche alle Sub-Zonen, die echte OSM-Relationen sind, aber noch keine Geometrie haben
    cur.execute("""
        SELECT ars_code, zone_name 
        FROM public.sub_zones 
        WHERE admin_level IN (8, 9, 10) AND geometry IS NULL;
    """)
    missing_zones = cur.fetchall()

    if not missing_zones:
        print("ℹ️ Alle Relationen besitzen bereits eine Geometrie. Kein Sync notwendig.")
        cur.close(); conn.close()
        return

    import time  # Ganz oben oder direkt hier platzieren
    
    print(f"\n🔄 Gefunden: {len(missing_zones)} Relationen ohne Geometrie. Starte OSM-Multipolygon-Sync...")

    try: # 🚀 NEU: Umschließt die Schleife zum Abfangen von Strg+C
        for ars_code, zone_name in missing_zones:
            if "_" not in ars_code: continue
            
            osm_id = ars_code.split("_")[-1]

            # 🚀 DER RETTUNGSRING: Vor jedem API-Abruf einer einzelnen Fläche 3 Sekunden warten!
            print(f"⏳ API-Schutz: Warte 3 Sekunden vor Abruf von '{zone_name}'...")
            time.sleep(3)

            print(f"🌐 Rufe Multipolygon für '{zone_name}' (OSM-ID: {osm_id}) ab...")
            query = f"[out:json][timeout:90]; relation({osm_id}); out geom;"
            
            # ... [Hier läuft dein normaler requests.post Code weiter]
            
            try:
                res = requests.post(OVERPASS_URL, data={'data': query}, headers=HEADERS, timeout=60)
                res.raise_for_status()
                data = res.json()
                
                elements = data.get("elements", [])
                if not elements:
                    print(f"⚠️ Keine Daten für ID {osm_id} gefunden.")
                    continue
                    
                # Extrahiere die Koordinatenketten der Außenringe (members/geometry)
                rel = elements[0]
                members = rel.get("members", [])
                
                # Wir nutzen PostGIS, um aus den Linienketten (LineStrings) ein sauberes Polygon zu bauen
                # Dazu sammeln wir die Punkte und übergeben sie als GeoJSON an PostGIS [1.21]
                polygons_geojson = []
                for member in members:
                    if member.get("type") == "way" and "geometry" in member:
                        coords = [[pt["lon"], pt["lat"]] for pt in member["geometry"]]
                        if coords:
                            polygons_geojson.append({
                                "type": "LineString",
                                "coordinates": coords
                            })
                
                if not polygons_geojson:
                    print(f"⚠️ Keine gültigen Linienzüge für '{zone_name}' extrahiert.")
                    continue

                # Wir kapseln die Linien in ein valides Feature-Set
                geojson_str = json.dumps({
                    "type": "GeometryCollection",
                    "geometries": polygons_geojson
                })

                # PostGIS-Magie: ST_Polygonize baut aus den Linienzügen geschlossene Flächen [1.21]
                # PostGIS-Fix: Das ST_Polygonize wird in ein Sub-SELECT verlagert,
                # um den Aggregat-Fehler beim UPDATE sauber zu umgehen!
                update_query = """
                    UPDATE public.sub_zones 
                    SET geometry = (
                        SELECT ST_Multi(ST_Polygonize(ST_GeomFromGeoJSON(%s)))
                    )
                    WHERE ars_code = %s;
                """
                cur.execute(update_query, (geojson_str, ars_code))
                conn.commit()
                print(f"✅ Geometrie für '{zone_name}' erfolgreich aus echten OSM-Grenzen aktualisiert.")

            except Exception as e:
                conn.rollback()
                print(f"❌ Fehler bei '{zone_name}': {e}")

    except KeyboardInterrupt: # 🚀 NEU: Fängt den Abbruch sauber ab
        print("\n\n🛑 NOTBREMSE IM SYNCER GEZOGEN! Schließe Ressourcen sauber...")
        cur.close()
        conn.close()
        return False # 🚀 NEU: Gibt False an das Hauptprogramm zurück

    cur.close()
    conn.close()
    print("\n🏁 Multipolygon-Sync-Lauf erfolgreich beendet!")
    return True # 🚀 NEU: Gibt True bei regulärem Ende zurück

if __name__ == "__main__":
    import json
    sync_missing_multipolygons()
