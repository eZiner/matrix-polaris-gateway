import asyncio
import sqlite3
from nio import AsyncClient, RoomMessageEncrypted
from shapely.geometry import Point, Polygon
import shapely.wkt  # Wird für das Einlesen von Polygonen aus PostgreSQL benötigt

# Für PostgreSQL (wird nur importiert und genutzt, wenn Produktion aktiv ist)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

# =====================================================================
# 1. DER ARCHITEKTUR-SCHALTER (FEATURE TOGGLE)
# =====================================================================
PROTOTYPING_MODE = True  # Setze auf False für den PostgreSQL-Produktivbetrieb!

# Matrix Zugangsdaten
MATRIX_HOMESERVER = "https://matrix.org"
BOT_USERNAME = "@dein_bot_name:matrix.org"
BOT_PASSWORD = "DeinSicheresPasswort"
GATEWAY_ROOM_ID = "!gateway_raum_id:matrix.org"

# Prototyping-Daten (Werden nur genutzt, wenn PROTOTYPING_MODE = True)
LOCAL_DB_FILE = "geofence_status.db"
LOCAL_REGIONEN = {
    "Goslar_Altstadt": {
        "polygon": Polygon([(10.420, 51.902), (10.435, 51.902), (10.435, 51.910), (10.420, 51.910)]),
        "room_id": "!goslar_raum_id:matrix.org"
    }
}

# PostgreSQL-Konfiguration (Wird nur genutzt, wenn PROTOTYPING_MODE = False)
POSTGRES_CONFIG = {
    "dbname": "polaris_gateway",
    "user": "postgres",
    "password": "DeinDbPasswort",
    "host": "localhost",
    "port": 5432
}

# =====================================================================
# 2. ABSTRAKTIONS-SCHICHT FÜR DATENBANKEN
# =====================================================================
def init_storage():
    """Initialisiert die Datenbanken je nach Modus."""
    if PROTOTYPING_MODE:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_status (
                user_id TEXT, region_name TEXT, is_inside INTEGER,
                PRIMARY KEY (user_id, region_name)
            )
        """)
        conn.commit()
        conn.close()
        print("📁 Speicher: Lokale SQLite-Datenbank initialisiert (Prototyping).")
    else:
        if not psycopg2:
            raise ImportError("psycopg2 fehlt! Installiere es mit: pip install psycopg2")
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        # Erstellt Tabellen für Regionen und Status in PostgreSQL
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS regions (
                name TEXT PRIMARY KEY,
                room_id TEXT NOT EXISTS,
                geometry_wkt TEXT -- Speichert das Polygon als Klartext-String (WKT)
            );
            CREATE TABLE IF NOT EXISTS user_status (
                user_id TEXT, region_name TEXT, is_inside BOOLEAN,
                PRIMARY KEY (user_id, region_name)
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("🐘 Speicher: Zentrale PostgreSQL-Datenbank initialisiert (Produktion).")

def load_regions_from_db():
    """Lädt die Regionen dynamisch. Im Prod-Modus direkt aus PostgreSQL."""
    if PROTOTYPING_MODE:
        return LOCAL_REGIONEN
    
    # Produktiv-Modus: Aus PostgreSQL laden
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT name, room_id, geometry_wkt FROM regions")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    prod_regionen = {}
    for row in rows:
        prod_regionen[row["name"]] = {
            "polygon": shapely.wkt.loads(row["geometry_wkt"]), # Konvertiert Text zurück in Shapely-Objekt
            "room_id": row["room_id"]
        }
    return prod_regionen

def get_last_status(user_id, region_name):
    """Liest den letzten Zustand aus der jeweils aktiven Datenbank."""
    if PROTOTYPING_MODE:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT is_inside FROM user_status WHERE user_id = ? AND region_name = ?", (user_id, region_name))
        row = cursor.fetchone()
        conn.close()
        return bool(row[0]) if row else False
    else:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT is_inside FROM user_status WHERE user_id = %s AND region_name = %s", (user_id, region_name))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[0] if row else False

def update_status(user_id, region_name, is_inside):
    """Speichert den Zustand in der jeweils aktiven Datenbank."""
    if PROTOTYPING_MODE:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_status (user_id, region_name, is_inside) VALUES (?, ?, ?)
            ON CONFLICT(user_id, region_name) DO UPDATE SET is_inside = excluded.is_inside
        """, (user_id, region_name, int(is_inside)))
        conn.commit()
        conn.close()
    else:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_status (user_id, region_name, is_inside) VALUES (%s, %s, %s)
            ON CONFLICT(user_id, region_name) DO UPDATE SET is_inside = EXCLUDED.is_inside
        """, (user_id, region_name, is_inside))
        conn.commit()
        cursor.close()
        conn.close()

# =====================================================================
# 3. GEOFENCE LOGIK & EVENT HANDLER (Bleibt für beide Modi identisch!)
# =====================================================================
async def message_callback(room, event):
    if room.room_id != GATEWAY_ROOM_ID:
        return

    try:
        if hasattr(event, "source") and "content" in event.source:
            content = event.source["content"]
            if "geo_uri" in content:
                geo_data = content["geo_uri"].replace("geo:", "").split(";")
                lat, lon = map(float, geo_data.split(","))
                user_id = event.sender
                
                user_point = Point(lon, lat)
                
                # Regionen werden dynamisch geladen (lokal oder aus Postgres)
                aktuelle_regionen = load_regions_from_db()
                
                for region_name, daten in aktuelle_regionen.items():
                    regional_room = daten["room_id"]
                    is_inside = daten["polygon"].contains(user_point)
                    was_inside = get_last_status(user_id, region_name)
                    
                    if is_inside and not was_inside:
                        print(f"🎯 {user_id} -> {region_name} (Betreten). Sende Invite...")
                        await client.room_invite(regional_room, user_id)
                        update_status(user_id, region_name, True)
                        
                    elif not is_inside and was_inside:
                        print(f"🚷 {user_id} -> {region_name} (Verlassen). Sende Kick...")
                        await client.room_kick(regional_room, user_id, reason="Zone verlassen.")
                        update_status(user_id, region_name, False)
                        
    except Exception as e:
        print(f"Fehler im Event-Handler: {e}")

# =====================================================================
# 4. BOT INITIATION
# =====================================================================
async def main():
    global client
    init_storage()  # Wählt automatisch das richtige DB-System
    
    client = AsyncClient(MATRIX_HOMESERVER, BOT_USERNAME)
    client.add_event_handler(RoomMessageEncrypted, message_callback)
    
    modus = "PROTOTYPING" if PROTOTYPING_MODE else "PRODUKTIONS"
    print(f"Bot startet im {modus}-Modus...")

    await client.login(BOT_PASSWORD)
    await client.sync_forever(timeout=30000, full_state=True)

if __name__ == "__main__":
    asyncio.run(main())
