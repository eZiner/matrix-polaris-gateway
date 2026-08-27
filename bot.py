import asyncio
import sqlite3
from nio import AsyncClient, RoomMessageEncrypted
from shapely.geometry import Point, Polygon
import shapely.wkt

# Für PostgreSQL (wird im Produktivmodus genutzt)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

# =====================================================================
# 1. DER ARCHITEKTUR-SCHALTER & CONFIG
# =====================================================================
PROTOTYPING_MODE = True  # Setze auf False für echten PostGIS-Betrieb!

# Matrix Zugangsdaten
MATRIX_HOMESERVER = "https://matrix.org"
BOT_USERNAME = "@dein_bot_name:matrix.org"
BOT_PASSWORD = "DeinSicheresPasswort"
GATEWAY_ROOM_ID = "!gateway_raum_id:matrix.org"

# Prototyping-Daten (SQLite + Shapely)
LOCAL_DB_FILE = "geofence_status.db"

#LOCAL_REGIONEN = {
#    "Goslar_Altstadt": {
#        "polygon": Polygon([(10.420, 51.902), (10.435, 51.902), (10.435, 51.910), (10.420, 51.910)]),
#        "room_id": "!goslar_raum_id:matrix.org"
#    }
#}

# =====================================================================
# DICTIONARY-STRUKTUR FÜR DIE REGION OBERHARZ (WILDEMANN)
# =====================================================================
LOCAL_REGIONEN = {
    "Wildemann_Ortskern": {
        "polygon": Polygon([
            (10.275, 51.820),  # Süd-West-Ecke (Längengrad, Breitengrad)
            (10.292, 51.820),  # Süd-Ost-Ecke
            (10.292, 51.838),  # Nord-Ost-Ecke (reicht hoch Richtung Hüttenberg)
            (10.275, 51.838),  # Nord-West-Ecke
            (10.275, 51.820)   # Schließt das Polygon
        ]),
        "room_id": "!wildemann_zentrum:matrix.org"
    },
    "Lautenthal_Nord": {
        "polygon": Polygon([
            (10.278, 51.860), 
            (10.298, 51.860), 
            (10.298, 51.875), 
            (10.278, 51.875),
            (10.278, 51.860)
        ]),
        "room_id": "!lautenthal_info:matrix.org"
    },
    "Clausthal_Zellerfeld": {
        "polygon": Polygon([
            (10.310, 51.795), 
            (10.355, 51.795), 
            (10.355, 51.820), 
            (10.310, 51.820),
            (10.310, 51.795)
        ]),
        "room_id": "!clausthal_zellerfeld_uni:matrix.org"
    },
    "Bad_Grund_Bergstadt": {
        "polygon": Polygon([
            (10.220, 51.802), 
            (10.250, 51.802), 
            (10.250, 51.818), 
            (10.220, 51.818),
            (10.220, 51.802)
        ]),
        "room_id": "!bad_grund_bergstadt:matrix.org"
    }
}

# PostgreSQL / PostGIS Konfiguration
POSTGRES_CONFIG = {
    "dbname": "polaris_gateway",
    "user": "postgres",
    "password": "DeinDbPasswort",
    "host": "localhost",
    "port": 5432
}

# =====================================================================
# 2. DATENBANK INITIALISIERUNG
# =====================================================================
def init_storage():
    """Initialisiert die Tabellen je nach Modus."""
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
        print("📁 Speicher: Lokale SQLite-Datenbank aktiv.")
    else:
        if not psycopg2:
            raise ImportError("psycopg2 fehlt! Installiere es mit: pip install psycopg2-binary")
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        # PostGIS-Tabelle mit echtem GEOMETRY-Typ
        cursor.execute("""
            CREATE EXTENSION IF NOT EXISTS postgis;
            CREATE TABLE IF NOT EXISTS regions (
                name VARCHAR(100) PRIMARY KEY,
                room_id VARCHAR(255) NOT NULL,
                geom GEOMETRY(Polygon, 4326) NOT NULL
            );
            CREATE INDEX IF NOT EXISTS regions_geom_idx ON regions USING gist(geom);
            CREATE TABLE IF NOT EXISTS user_status (
                user_id VARCHAR(255),
                region_name VARCHAR(100) REFERENCES regions(name) ON DELETE CASCADE,
                is_inside BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (user_id, region_name)
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("🐘 Speicher: Echte PostgreSQL/PostGIS-Datenbank aktiv.")

# =====================================================================
# 3. STATISCHE & METADATEN-ABFRAGEN
# =====================================================================
def load_all_regions_metadata():
    """Lädt eine einfache Liste aller Region-Namen und Raum-IDs für den Abgleich."""
    if PROTOTYPING_MODE:
        return {name: d["room_id"] for name, d in LOCAL_REGIONEN.items()}
    
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT name, room_id FROM regions")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row["name"]: row["room_id"] for row in rows}

def get_last_status(user_id, region_name):
    """Holt den letzten Zustand des Nutzers (True = Drinnen, False = Draußen)."""
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
    """Speichert den aktuellen Zustand des Nutzers ab."""
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
# 4. GEOFENCE CORE-LOGIK
# =====================================================================
def check_user_location_db(latitude, longitude):
    """
    Ermittelt, in welchen Regionen der Punkt liegt.
    Nutzt im Prod-Modus das hochperformante ST_Contains von PostGIS.
    """
    if PROTOTYPING_MODE:
        user_point = Point(longitude, latitude)
        return [name for name, d in LOCAL_REGIONEN.items() if d["polygon"].contains(user_point)]
    
    # PRODUKTIVBETRIEB: PostGIS-Abfrage (In welchen Polygonen liegt der Punkt?)
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    sql = """
        SELECT name FROM regions 
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
    """
    cursor.execute(sql, (longitude, latitude))
    treffer = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row["name"] for row in treffer]

# =====================================================================
# 5. MATRIX EVENT HANDLER
# =====================================================================
async def message_callback(room, event):
    if room.room_id != GATEWAY_ROOM_ID:
        return

    try:
        if hasattr(event, "source") and "content" in event.source:
            content = event.source["content"]
            if "geo_uri" in content:
                # Extrahiere GPS aus "geo:51.912,10.425"
                geo_data = content["geo_uri"].replace("geo:", "").split(";")[0]
                lat, lon = map(float, geo_data.split(","))
                user_id = event.sender
                
                # 1. Datenbank nach Treffern fragen (PostGIS optimiert!)
                aktive_regionen = check_user_location_db(lat, lon)
                
                # 2. Alle existierenden Regionen durchgehen für den Statusabgleich
                alle_regionen = load_all_regions_metadata()
                
                for region_name, room_id in alle_regionen.items():
                    is_inside = region_name in aktive_regionen
                    was_inside = get_last_status(user_id, region_name)
                    
                    if is_inside and not was_inside:
                        print(f"🎯 {user_id} -> {region_name} (Betreten). Sende Invite...")
                        await client.room_invite(room_id, user_id)
                        update_status(user_id, region_name, True)
                        
                    elif not is_inside and was_inside:
                        print(f"🚷 {user_id} -> {region_name} (Verlassen). Sende Kick...")
                        await client.room_kick(room_id, user_id, reason="Zone verlassen.")
                        update_status(user_id, region_name, False)
                        
    except Exception as e:
        print(f"Fehler im Event-Handler: {e}")

# =====================================================================
# 6. ENGINE START
# =====================================================================
async def main():
    global client
    init_storage()
    
    client = AsyncClient(MATRIX_HOMESERVER, BOT_USERNAME)
    client.add_event_handler(RoomMessageEncrypted, message_callback)
    
    modus = "PROTOTYPING" if PROTOTYPING_MODE else "PRODUKTIONS"
    print(f"Bot startet im {modus}-Modus...")
    
    await client.login(BOT_PASSWORD)
    await client.sync_forever(timeout=30000, full_state=True)

if __name__ == "__main__":
    asyncio.run(main())
