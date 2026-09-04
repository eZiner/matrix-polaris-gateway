import os
import asyncio
import logging
import time
from typing import Dict, Set
from nio import AsyncClient, MatrixRoom, RoomMessageText

# PostGIS Anbindung (Asynchron)
import asyncpg

# Logging Konfiguration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("POLARIS-Gateway")

# --- SOUVERÄNE ARCHITEKTUR-KONSTANTEN ---
HOMESERVER_URL = "https://goslar.de"  # Physisch im Uni-Rechenzentrum
BOT_USER_ID = "@polaris-gateway:goslar.de"
BOT_PASSWORD = "DeinStrengGeheimesBotPasswortHier"

# Das exklusive, vordefinierten Chatfenster NUR für den Geo-Fencing-Bot
GEOFENCING_BOT_ROOM_ID = "!vordefinierterBotRaumID:goslar.de"

# Hysterese-Schutz Konfiguration (10 Minuten Cooldown)
COOLDOWN_SECONDS = 600

# --- IN-MEMORY RAM SPEICHER (Flüchtig, keine Persistenz auf Festplatte) ---
# Struktur: { user_id: { space_id_1, space_id_2 } }
ACTIVE_USER_SPACES: Dict[str, Set[str]] = {}

# Struktur: { (user_id, space_id): timestamp_when_outside }
EXIT_PENDING_USERS: Dict[tuple, float] = {}


async def check_geofencing_postgis(lon: float, lat: float) -> Set[str]:
    """
    Gleicht die Koordinate flüchtig im RAM mit der PostGIS-Datenbank ab.
    Liefert direkt das Set der passenden übergeordneten INFOSPACES zurück.
    """
    database_url = os.getenv("DATABASE_URL")
    conn = await asyncpg.connect(user='polaris', password=database_url,
                                 database='polaris_geo', host='127.0.0.1')
    try:
        # Die schlanke Query zieht direkt die ID des übergeordneten Containers (Infospace)
        query = """
            SELECT matrix_space_id 
            FROM polaris_infospaces 
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326));
        """
        rows = await conn.fetch(query, lon, lat)
        # Die exakte Koordinate wird nach der Query im RAM nicht mehr angefasst/gespeichert
        return {row['matrix_space_id'] for row in rows}
    finally:
        await conn.close()


async def message_callback(room: MatrixRoom, event: RoomMessageText) -> None:
    """
    Asynchrone Event-Schleife. Reagiert strikt nur im vordefinierten Raum.
    """
    # STRIKTE FILTERUNG: Ignoriere alles außerhalb des dedizierten Bot-Raums (Sicherheits-Schutzwall)
    if room.room_id != GEOFENCING_BOT_ROOM_ID:
        return

    # Ignoriere eigene Nachrichten des Bots
    if event.sender == BOT_USER_ID:
        return

    # Prüfen, ob das Event ein standardisiertes Matrix-Standort-Event ist
    # HINWEIS: Element sendet m.location oft im content-Block regulärer Events
    if "geo:" in event.body or (event.content and "geo:" in event.content.get("geo_uri", "")):
        try:
            # Extraktion der Koordinaten flüchtig in lokale RAM-Variablen
            geo_uri = event.content.get("geo_uri", event.body)
            coords = geo_uri.split("geo:")[1].split(";")[0].split(",")
            lat, lon = float(coords[0]), float(coords[1])
            
            user_id = event.sender
            logger.info(f"Standort-Signal empfangen von {user_id}. Starte flüchtigen RAM-Abgleich...")

            # 1. PostGIS-Abfrage starten
            matched_spaces = await check_geofencing_postgis(lon, lat)

            # Initialisiere User im flüchtigen Speicher, falls neu
            if user_id not in ACTIVE_USER_SPACES:
                ACTIVE_USER_SPACES[user_id] = set()

            # 2. EVALUIERUNG: NEUE INFE-SPACES BETRETEN (Geräuschloser Auto-Join)
            for space_id in matched_spaces:
                # Wenn der Nutzer noch nicht im Space ist und nicht auf dem Sprung steht
                if space_id not in ACTIVE_USER_SPACES[user_id]:
                    
                    # Falls der Nutzer im Cooldown für diesen Space war, breche den Exit ab
                    if (user_id, space_id) in EXIT_PENDING_USERS:
                        del EXIT_PENDING_USERS[(user_id, space_id)]
                        logger.info(f"Hysterese abgebrochen für {user_id} in {space_id} (Re-Entry).")
                    else:
                        # Nativer, geräuschloser Server-Beitritt über restricted Join Rules des Verbunds
                        # Das Heimat-Gateway triggert den Join direkt über die Föderation (Port 8448)
                        await client.room_join(space_id)
                        ACTIVE_USER_SPACES[user_id].add(space_id)
                        logger.info(f"Geräuschloser Auto-Join ausgeführt: {user_id} -> Infospace {space_id}")

            # 3. EVALUIERUNG: SPACES VERLASSEN (Hysterese-Vorbereitung)
            for current_space_id in list(ACTIVE_USER_SPACES[user_id]):
                if current_space_id not in matched_spaces:
                    # Nicht sofort kicken, sondern auf die Exit-Warteliste setzen (GPS-Springen abfedern)
                    if (user_id, current_space_id) not in EXIT_PENDING_USERS:
                        EXIT_PENDING_USERS[(user_id, current_space_id)] = time.time()
                        logger.info(f"User {user_id} hat Zone verlassen. Setze {current_space_id} auf Cooldown-Liste.")

        except Exception as e:
            logger.error(f"Fehler bei der flüchtigen Geo-Verarbeitung: {e}")


async def cooldown_cleanup_loop() -> None:
    """
    Unauffällige asynchrone Hintergrundschleife für den Hysterese-Schutz.
    Führt nach Ablauf der Karenzzeit den automatischen Server-Kick aus.
    """
    while True:
        await asyncio.sleep(10)  # Prüfe alle 10 Sekunden den Zustand der Warteliste
        now = time.time()
        
        for (user_id, space_id), timestamp in list(EXIT_PENDING_USERS.items()):
            # Wenn die 10 Minuten (600 Sekunden) abgelaufen sind
            if now - timestamp >= COOLDOWN_SECONDS:
                try:
                    # Automatisierter Server-Kick aus dem gesamten Infospace-Container
                    # Dadurch verschwindet der Ordner inklusive Unterkanäle spurlos beim Bürger
                    await client.room_kick(space_id, user_id, reason="Zone dauerhaft verlassen (Datenhygiene).")
                    
                    # Bereinigung im flüchtigen RAM-Speicher
                    if user_id in ACTIVE_USER_SPACES and space_id in ACTIVE_USER_SPACES[user_id]:
                        ACTIVE_USER_SPACES[user_id].remove(space_id)
                    
                    del EXIT_PENDING_USERS[(user_id, space_id)]
                    logger.info(f"Datenhygiene erfolgreich: {user_id} aus Infospace {space_id} entfernt.")
                    
                except Exception as e:
                    logger.error(f"Fehler beim automatischen Server-Kick für {user_id} in {space_id}: {e}")


async def main() -> None:
    global client
    # Verbindung zum lokalen Homeserver an der Universität aufbauen
    client = AsyncClient(HOMESERVER_URL, BOT_USER_ID)
    client.add_message_callback(message_callback, RoomMessageText)

    logger.info("Verbinde mit dem universitären Kommunal-Homeserver...")
    await client.login(BOT_PASSWORD)
    
    # Starte die Event-Schleife und die Hysterese-Schleife parallel im asynchronen Verbund
    await asyncio.gather(
        client.sync_forever(timeout=30000),
        cooldown_cleanup_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())