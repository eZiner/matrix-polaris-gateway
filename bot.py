import asyncio
import time  # NEU: Für zeitbasierte Hysterese
from nio import AsyncClient, RoomMessageText, MatrixRoom
from shapely.geometry import Point, Polygon

# --- CONFIGURATION ---
MATRIX_HOMESERVER = "https://clausthal-zellerfeld.de"
BOT_USER_ID = "@polaris-bot:clausthal-zellerfeld.de"
BOT_PASSWORD = "IhrSicheresPasswort123!"

# Pufferzeit in Sekunden: Wie lange warten wir nach einem Exit, bevor wir wirklich kicken?
# Für Tests auf 30 Sekunden gestellt (Im Echtbetrieb: 600 für 10 Minuten)
EXIT_COOLDOWN_TIME = 30 

ZONEN_REGISTER = {
    "Clausthal-Zellerfeld": {
        "room_id": "!clz-info12345:matrix.org",
        "polygon": Polygon([
            (10.3100, 51.8000), (10.3600, 51.8000),
            (10.3600, 51.8300), (10.3100, 51.8300),
            (10.3100, 51.8000)
        ])
    },
    "Goslar": {
        "room_id": "!goslar-info67890:matrix.org",
        "polygon": Polygon([
            (10.4000, 51.8900), (10.4500, 51.8900),
            (10.4500, 51.9200), (10.4000, 51.9200),
            (10.4000, 51.8900)
        ])
    }
}

# --- TRACKING STORAGE ---
ACTIVE_USER_SUBSCRIPTIONS = {} # Wer ist im Raum aktiv
EXIT_PENDING_USERS = {}        # NEU: Warteliste für den Kick { "@user": { "!raum_id": timestamp_des_exits } }

async def process_geo_position(sender: str, lat: float, lon: float, trigger_room_id: str) -> None:
    buerger_punkt = Point(lon, lat)
    current_time = time.time()
    
    if sender not in ACTIVE_USER_SUBSCRIPTIONS:
        ACTIVE_USER_SUBSCRIPTIONS[sender] = set()
    if sender not in EXIT_PENDING_USERS:
        EXIT_PENDING_USERS[sender] = {}

    aktuelle_treffer_raeume = set()

    # 1. ENTER-SCHLEIFE & RETTUNG AUS COOLDOWN
    for zonen_name, zonen_daten in ZONEN_REGISTER.items():
        ziel_raum = zonen_daten["room_id"]
        
        if zonen_daten["polygon"].contains(buerger_punkt):
            aktuelle_treffer_raeume.add(ziel_raum)
            
            # Fall A: Nutzer war im Cooldown für diesen Raum (Signal sprang kurz raus und wieder rein)
            if ziel_raum in EXIT_PENDING_USERS[sender]:
                del EXIT_PENDING_USERS[sender][ziel_raum]
                print(f"[PING-PONG SCHUTZ] {sender} ist rechtzeitig in die Zone '{zonen_name}' zurückgekehrt. Kick abgebrochen.")
            
            # Fall B: Echter Neueintritt
            elif ziel_raum not in ACTIVE_USER_SUBSCRIPTIONS[sender]:
                print(f"--> [ENTER] {sender} hat die Zone '{zonen_name}' betreten.")
                await client.room_send(
                    room_id=trigger_room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": f"POLARIS-Update: Willkommen in {zonen_name}! Du wurdest zum Infokanal eingeladen."}
                )
                await client.room_invite(room_id=ziel_raum, user_id=sender)
                ACTIVE_USER_SUBSCRIPTIONS[sender].add(ziel_raum)

    # 2. EXIT-SCHLEIFE: Auf die Warteliste setzen statt direkt kicken
    for aktiver_raum in list(ACTIVE_USER_SUBSCRIPTIONS[sender]):
        if aktiver_raum not in aktuelle_treffer_raeume and aktiver_raum not in EXIT_PENDING_USERS[sender]:
            # Wir kicken noch nicht, wir merken uns nur den Zeitpunkt des Verlassens
            EXIT_PENDING_USERS[sender][aktiver_raum] = current_time
            zonen_name = [name for name, d in ZONEN_REGISTER.items() if d["room_id"] == aktiver_raum][0]
            print(f"[COOLDOWN START] {sender} hat die Zone '{zonen_name}' verlassen. Pufferzeit läuft...")

# --- NEU: HINTERGRUND-TASK FÜR DIE KICK-BEREINIGUNG ---
async def cooldown_cleanup_loop():
    """Prüft jede Sekunde, ob die Pufferzeit von Nutzern auf der Warteliste abgelaufen ist."""
    while True:
        current_time = time.time()
        for user_id, raeume in list(EXIT_PENDING_USERS.items()):
            for raum_id, exit_timestamp in list(raeume.items()):
                # Wenn die Cooldown-Zeit abgelaufen ist, wird der Kick final ausgeführt
                if current_time - exit_timestamp >= EXIT_COOLDOWN_TIME:
                    zonen_name = [name for name, d in ZONEN_REGISTER.items() if d["room_id"] == raum_id][0]
                    print(f"--> [FINAL EXIT] Puffer abgelaufen. Kicke {user_id} aus '{zonen_name}'.")
                    
                    try:
                        # Kick auf dem Server ausführen
                        await client.room_kick(room_id=raum_id, user_id=user_id, reason="POLARIS: Geofence dauerhaft verlassen.")
                        # Aus internem Zustand löschen
                        ACTIVE_USER_SUBSCRIPTIONS[user_id].remove(raum_id)
                        del EXIT_PENDING_USERS[user_id][raum_id]
                    except Exception as e:
                        print(f"Fehler beim Ausführen des finalen Kicks: {e}")
                        
        await asyncio.sleep(1) # Schleife schläft für 1 Sekunde zur CPU-Schonung

async def custom_event_callback(room: MatrixRoom, event: any) -> None:
    sender = event.sender
    source_type = event.source.get('type')
    content = event.source.get('content', {})

    if (source_type == "m.room.message" and content.get('msgtype') == 'm.location') or \
       (source_type in ["org.matrix.m.beacon", "m.beacon"]):
        try:
            location_entry = content.get('org.matrix.m.location', content.get('m.location', {}))
            geo_uri = content.get('geo_uri') or location_entry.get('geo_uri')
            coords = geo_uri.split(":")[1].split(";")[0].split(",")
            lat, lon = map(float, coords)
            
            await process_geo_position(sender, lat, lon, room.room_id)
        except Exception as e:
            print(f"Fehler bei Geo-Verarbeitung: {e}")

async def main():
    global client
    client = AsyncClient(MATRIX_HOMESERVER, BOT_USER_ID)
    client.add_event_handler(custom_event_callback, "*")
    
    print("Projekt POLARIS - Multi-Zonen-Gateway inklusive Ping-Pong-Schutz startet...")
    await client.login(BOT_PASSWORD)
    
    # NEU: Wir starten die Reinigungs-Schleife als asynchronen Hintergrund-Task parallel zum Matrix-Sync
    asyncio.create_task(cooldown_cleanup_loop())
    
    print("System aktiv. Bereit für Tests mit intelligentem Hysterese-Puffer!")
    await client.sync_forever(timeout=30000)

if __name__ == "__main__":
    asyncio.run(main())
