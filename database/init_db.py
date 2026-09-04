# test_db.py (Speicherort: /database)
import os
import sys
import psycopg2
from dotenv import load_dotenv

# 1. PFAD ERMITTELN
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(project_root, 'production', '.env')

# 2. UMGEBUNGSVARIABLEN LADEN
load_dotenv(dotenv_path=env_path)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print(f"❌ FEHLER: Die Umgebungsvariable 'DATABASE_URL' wurde nicht gefunden!", file=sys.stderr)
    sys.exit(1)

print("🚀 Verbinde mit PostGIS für den Datenbank-Check und Tabellen-Erstellung...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    print("\n🔍 --- DATENBANK-DEBUG ---")
    
    # 1. Welche Datenbank und welcher User sind im Skript aktiv?
    cur.execute("SELECT current_database(), current_user;")
    db_info = cur.fetchone()
    print(f"Aktive Datenbank im Skript: {db_info} | Benutzer: {db_info}")
    
    # 2. Tabelle live erstellen (PostGIS wird als bereits aktiv vorausgesetzt)
    print("⏳ Erstelle Tabelle 'polaris_infospaces', falls sie nicht existiert...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.polaris_infospaces (
            matrix_space_id VARCHAR(255) PRIMARY KEY,
            zone_name VARCHAR(255),
            osm_id BIGINT,
            osm_tag_key VARCHAR(100),
            osm_tag_value VARCHAR(100),
            geom geometry(MultiPolygon, 4326)
        );
    """)
    conn.commit()
    print("✅ Tabelle erfolgreich geprüft / erstellt!")
    
    # 3. Alle Tabellen im Schema 'public' auflisten zur Kontrolle
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public';
    """)
    tabellen = cur.fetchall()
    
    print("\nVerfügbare Tabellen im Schema 'public':")
    for t in tabellen:
        print(f" -> {t}")
    print("--------------------------\n")
    
    cur.close()
    conn.close()
    print("🎉 Test und Erstellung erfolgreich abgeschlossen!")

except Exception as db_e:
    print(f"❌ Fehler bei der Datenbank-Vorbereitung: {db_e}", file=sys.stderr)
    sys.exit(1)
