import asyncio
from nio import AsyncClient, RoomMessageText, MatrixRoom
from shapely.geometry import Point, Polygon

# --- CONFIGURATION ---
MATRIX_HOMESERVER = "https://clausthal-zellerfeld.de"
BOT_USER_ID = "@polaris-bot:clausthal-zellerfeld.de"
BOT_PASSWORD = "IhrSicheresPasswort123!"

# --- MULTI-ZONEN DEFINITION (Die "Landkarte" im Speicher) ---
# Wir definieren zwei separate Chat-Zellen mit ihren jeweiligen Matrix-Raum-IDs
ZONEN_REGISTER = {
    "Clausthal-Zellerfeld": {
        "room_id": "!clz-info12345:matrix.org",  # Beispiel-ID für CLZ-Kanal
        "polygon": Polygon([
            (10.3100, 51.8000), (10.3600, 51.8000),
            (10.3600, 51.8300), (10.3100, 51.8300),
            (10.3100, 51.8000)
        ])
    },
    "Goslar": {
        "room_id": "!goslar-info67890:matrix.org", # Beispiel-ID für Goslar-Kanal
        "polygon": Polygon([
            (10.4000, 51.8900), (10.4500, 51.8900),
            (10.4500, 51.9200), (10.4000, 51.9200),
            (10.4000, 51.8900)
        ])
    }
}

# --- ZUSTANDS-TRACKING (Wer ist aktuell wo angemeldet?) ---
# Struktur: { "@user:server.de": set(["!raum_id1"]) }
ACTIVE_USER_SUBSCRIPTIONS = {}

# --- KERN-LOGIK FÜR DATENBANK-MATCHING ---
async def process_geo_position(sender: str, lat: float, lon: float, trigger_room_id: str) -> None:
    """Prüft alle Zonen und steuert dynamisch Invites und Kicks."""
    buerger_punkt = Point(lon, lat) # Wichtig: (Longitude, Latitude) für Shapely
    
    if sender not in ACTIVE_USER_SUBSCRIPTIONS:
        ACTIVE_USER_SUBSCRIPTIONS[sender] = set()

    aktuelle_treffer_zonen = set()

    # 1. Schritt: Alle hinterlegten Geofences nach einem Treffer durchsuchen
    for zonen_name, zonen_daten in ZONEN_REGISTER.items():
        ziel_raum = zonen_daten["room_id"]
        
        if zonen_daten["polygon"].contains(buerger_punkt):
            aktuelle_treffer_zonen.add(ziel_raum)
            
            # --- ENTER-LOGIK: Nutzer hat eine neue Zone betreten ---
            if ziel_raum not in ACTIVE_USER_SUBSCRIPTIONS[sender]:
                print(f"--> [ENTER] {sender} hat die Zone '{zonen_name}' betreten.")
                await client.room_send(
                    room_id=trigger_room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": f"POLARIS-Update: Du hast die Region {zonen_name} betreten. Automatischer Beitritt zum lokalen Infokanal."}
                )
                # Einladung in den spezifischen Raum dieser Stadt senden
                await client.room_invite(room_id=ziel_raum, user_id=sender)
                ACTIVE_USER_SUBSCRIPTIONS[sender].add(ziel_raum)

    # 2. Schritt: EXIT-LOGIK prüfen (Räume, in denen der Nutzer ist, die aber kein Treffer mehr sind)
    # Wir erstellen eine Kopie der Liste, um sie während der Schleife sicher zu verändern
    historische_raeume = list(ACTIVE_USER_SUBSCRIPTIONS[sender])
    
    for alter_raum in historische_raeume:
        if alter_raum not in aktuelle_treffer_zonen:
            # Name der verlassenen Zone für den Chat-Text ermitteln
            zonen_name = [name for name, d in ZONEN_REGISTER.items() if d["room_id"] == alter_raum][0]
            print(f"--> [EXIT] {sender} hat die Zone '{zonen_name}' verlassen.")
            
            await client.room_send(
                room_id=trigger_room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": f"POLARIS-Update: Du hast die Region {zonen_name} verlassen. Automatischer Austritt aus dem Infokanal."}
            )
            # Kick-Befehl ausführen, um den alten Raum zu bereinigen
            await client.room_kick(room_id=alter_raum, user_id=sender, reason=f"Geofence-Exit: {zonen_name} verlassen")
            ACTIVE_USER_SUBSCRIPTIONS[sender].remove(alter_raum)

# --- CENTRAL EVENT HANDLER ---
async def custom_event_callback(room: MatrixRoom, event: any) -> None:
    sender = event.sender
    source_type = event.source.get('type')
    content = event.source.get('content', {})

    # Wir verarbeiten sowohl manuelle Shares als auch kontinuierliche Live-Beacons im Auto
    if (source_type == "m.room.message" and content.get('msgtype') == 'm.location') or \
       (source_type in ["org.matrix.m.beacon", "m.beacon"]):
        try:
            location_entry = content.get('org.matrix.m.location', content.get('m.location', {}))
            geo_uri = content.get('geo_uri') or location_entry.get('geo_uri')
            coords = geo_uri.split(":").split(";")
            lat, lon = map(float, coords.split(","))
            
            print(f"\n[STANDORT-SIGNAL] Koordinaten empfangen: Lat {lat}, Lon {lon} von {sender}")
            await process_geo_position(sender, lat, lon, room.room_id)
        except Exception as e:
            print(f"Fehler bei Geo-Verarbeitung: {e}")

async def main():
    global client
    client = AsyncClient(MATRIX_HOMESERVER, BOT_USER_ID)
    client.add_event_handler(custom_event_callback, "*")
    
    print("Projekt POLARIS - Multi-Zonen-Gateway startet...")
    await client.login(BOT_PASSWORD)
    print("System aktiv. Bereit für die Simulation von Autofahrten zwischen CLZ und Goslar!")
    await client.sync_forever(timeout=30000)

if __name__ == "__main__":
    asyncio.run(main())
