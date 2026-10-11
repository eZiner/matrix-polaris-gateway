import asyncio
import os
import csv
import logging
import sys
import urllib.parse
from datetime import datetime
import psycopg2  # Echte PostgreSQL/PostGIS Schnittstelle
from dotenv import load_dotenv  # Zieht die Daten sicher aus der .env
from nio import AsyncClient, MatrixRoom, InviteEvent, RoomMessageText, Event, UnknownEvent

# ALLE UMGEBUNGSVARIABLEN AUS DER .ENV LADEN
load_dotenv()

# Schaltet das blockierende Krypto-Fehler-Logging von matrix-nio stumm
logging.getLogger("nio.crypto").setLevel(logging.CRITICAL)

# --- CONFIGURATION VIA ENVIRONMENT VARIABLES ---
HOMESERVER = os.getenv("MATRIX_HOMESERVER", "https://ziner.de")
BOT_USER = os.getenv("MATRIX_BOT_USER", "@rathaus:matrix.ziner.de")
BOT_PASSWORD = os.getenv("MATRIX_BOT_PASSWORD", "DEIN_PASSWORT")
ADMIN_USER = os.getenv("MATRIX_ADMIN_USER", "@eziner:matrix.ziner.de")

STORE_PATH = "./bot_store/"
CREDENTIALS_FILE = "bot_credentials.txt"
CSV_FILE = "schadensmeldungen.csv"
HUND_CSV = "hunderegister.csv"

if not os.path.exists(STORE_PATH):
    os.makedirs(STORE_PATH)

USER_STATES = {}
HUND_STATES = {}

def get_next_ticket_id(datei):
    if not os.path.exists(datei):
        return 1
    try:
        with open(datei, mode="r", encoding="utf-8") as f:
            return len(list(csv.reader(f)))
    except Exception:
        return 1

# CSVs initialisieren
for datei, header in [(CSV_FILE, ["Ticket_ID", "Zeitstempel", "Sender", "Raum_ID", "Kategorie", "Ort", "Beschreibung"]),
                      (HUND_CSV, ["Meldungs_ID", "Zeitstempel", "Sender", "Raum_ID", "Hunderasse", "Name_des_Hundes"])]:
    if not os.path.exists(datei):
        with open(datei, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

# 🛰️ DIE PERFEKTIONIERTE POSTGIS ENGINE (Mit deinen korrigierten Spaltennamen!)
def query_postgis_geofence(lat, lon):
    print(f"🛰️ POSTGIS: Analysiere Territorium für GPS-Fix Lat={lat}, Lon={lon}...")
    
    result = {
        "matched": False,
        "main_zone": "Unbekanntes Gebiet",
        "ars": "Kein ARS-Code",
        "sub_zones": []
    }
    
    db_url = os.getenv("DATABASE_URL")
    
    # 🎯 DEINE ERFOLGREICHE KRÜCKE: Für den lokalen Betrieb außerhalb der Bridge
    if db_url and "@polaris-db" in db_url:
        db_url = db_url.replace("@polaris-db", "@127.0.0.1")
    elif db_url and "@postgres" in db_url:
        db_url = db_url.replace("@postgres", "@127.0.0.1")
        
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # 📍 QUERY 1: Hauptzone abfragen (Mit zone_name)
        sql_main = """
            SELECT zone_name, ars_code 
            FROM main_zones 
            WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(%s, %s), 4326))
            LIMIT 1;
        """
        cursor.execute(sql_main, (lon, lat))
        main_row = cursor.fetchone()
        
        if main_row:
            result["matched"] = True
            result["main_zone"] = main_row[0]  # zone_name (z.B. Clausthal-Zellerfeld)
            result["ars"] = main_row[1]        # ars_code
            print(f"🟢 HAUPTZONE: {result['main_zone']} (ARS: {result['ars']})")
        
        # 📍 QUERY 2: Sub-Zonen abfragen (Mit zone_name und admin_level)
        sql_sub = """
            SELECT zone_name, admin_level 
            FROM sub_zones 
            WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(%s, %s), 4326))
            ORDER BY admin_level DESC;
        """
        cursor.execute(sql_sub, (lon, lat))
        sub_rows = cursor.fetchall()
        
        if sub_rows:
            for row in sub_rows:
                # KORREKTUR: Wir lesen die Indizes der Zeile explizit aus!
                s_name = row[0]
                s_level = row[1]
                result["sub_zones"].append(f"{s_name:<25} | Ebene/Typ: {s_level}")
            print(f"🏡 SUB-ZONEN: {len(result['sub_zones'])} Treffer.")
            
        cursor.close()
        conn.close()
    except Exception as db_err:
        print(f"❌ PostGIS-Datenbankfehler: {db_err}")
        
    return result

async def listen_for_invites(room: MatrixRoom, event: InviteEvent) -> None:
    try: await client.join(room.room_id)
    except Exception: pass

# --- DAS INTERVALL-STABILE GEOFENCE-GATEWAY INTERFACE ---
async def listen_for_events(room: MatrixRoom, event: Event) -> None:
    if event.sender == BOT_USER:
        return

    room_id = room.room_id
    user_id = event.sender

    if isinstance(event, RoomMessageText):
        await process_text_message(room_id, user_id, event.body.strip())
        return

    event_source = getattr(event, "source", {})
    event_content = event_source.get("content", {})
    event_type = event_source.get("type", "")

    if not event_content:
        return

    msgtype = event_content.get("msgtype")
    geo_uri = None

    if msgtype == "m.location":
        print(f"📥 GEO-GATEWAY: Klassischen Standort-Ping erhalten von {user_id}!")
        geo_uri = event_content.get("geo_uri")
        if not geo_uri and "org.matrix.msc3488.location" in event_content:
            geo_uri = event_content.get("org.matrix.msc3488.location", {}).get("uri")
        if geo_uri:
            await handle_gps_coordinates(room_id, user_id, geo_uri, "Klassischer Ping")
        return

    # 📍 KORREKTUR: STREAM-STATUS PRÜFEN (Initialisiert vs. Beendet)
    if event_type == "org.matrix.msc3672.beacon_info":
        is_live = event_content.get("live", True)
        
        if is_live:
            print(f"🛰️ GEO-GATEWAY: Live-Standort-Stream wurde von {user_id} initialisiert!")
            try: await client.keys_query()
            except Exception: pass
            
            reply_html = (
                f"<h3>🛰️ POLARIS GeoFence Gateway</h3>"
                f"<p>Live-Standort-Stream erfolgreich mit dem Föderations-Knotenpunkt verbunden.</p>"
                f"<p>Sobald sich deine GPS-Position im Harz ändert, wertet PostGIS deine Gemeinde-Zonen live aus! 🏔️</p>"
            )
            await send_encrypted_reply(room_id, "Live-Standort verbunden. Warte auf PostGIS-Routing...", reply_html)
        else:
            # Wenn das Handy den Stream abschaltet, steht im JSON "live": false
            print(f"🛑 GEO-GATEWAY: Live-Standort-Stream wurde von {user_id} beendet!")
            reply_html = (
                f"<h3>🛑 GeoFence Gateway: Verbindung getrennt</h3>"
                f"<p>Der Live-GPS-Stream für diesen Raum wurde ordnungsgemäß geschlossen.</p>"
                f"<p>POLARIS hat den Routing-Kanal für dein Gerät erfolgreich deaktiviert. Unterbrochen. 🔌</p>"
            )
            await send_encrypted_reply(room_id, "Live-Standort-Stream beendet. Verbindung getrennt.", reply_html)
        return

    if event_type == "org.matrix.msc3671.beacon" or "beacon" in event_type:
        loc_structure = event_content.get("org.matrix.msc3488.location", {})
        geo_uri = loc_structure.get("uri")
        
        if not geo_uri:
            for key, val in event_content.items():
                if isinstance(val, dict) and "uri" in val:
                    if str(val["uri"]).startswith("geo:"):
                        geo_uri = val["uri"]

        if geo_uri:
            await handle_gps_coordinates(room_id, user_id, geo_uri, "Live-Tracking 🛰️")
        return

async def handle_gps_coordinates(room_id: str, user_id: str, geo_uri: str, methode: str):
    if geo_uri.startswith("geo:"):
        try:
            coords_part = geo_uri[4:]
            
            # 📍 ENDGÜLTIGER FIX: Wir greifen uns nach dem Split explizit das erste Element (Index 0)!
            if ";" in coords_part:
                coords_part = coords_part.split(";")[0]
                
            # Jetzt ist coords_part GARANTIERT immer ein reiner String ("51.8285131,10.2836835")
            lat_str, lon_str = coords_part.split(",")
            latitude = float(lat_str)
            longitude = float(lon_str)
            
            # Zündet eure pure PostGIS DATABASE_URL Abfrage
            geo_match = query_postgis_geofence(latitude, longitude)
            
            # Generiert die saubere OSM-URL mit mlat-Parameter für Element
            osm_url = f"https://openstreetmap.org?{latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
            
            sub_zones_html = "".join([f"<li>► <code>{sz}</code></li>" for sz in geo_match["sub_zones"]])
            if not sub_zones_html:
                sub_zones_html = "<li>Außerhalb bekannter Sektoren</li>"
                
            reply_html = (
                f"<h3>🛰️ GeoFence Gateway: Föderations-Routing</h3>"
                f"<p>Empfangsmethode: <strong>{methode}</strong></p>"
                f"<ul>"
                f"<li>🌐 <strong>GPS-Koordinate:</strong> <code>{latitude}, {longitude}</code></li>"
                f"<li>🏛️ <strong>Hauptzone (Gemeinde):</strong> <strong>{geo_match['main_zone']}</strong></li>"
                f"<li>🎫 <strong>Amtlicher Regionalschlüssel (ARS):</strong> <code>{geo_match['ars']}</code></li>"
                f"</ul>"
                f"<h4>🏡 Erkannte Sektoren (Sub-Zonen):</h4>"
                f"<ul>{sub_zones_html}</ul>"
            )
            
            if geo_match["matched"]:
                reply_html += f"<p>✅ <strong>Routing-Status:</strong> Das Ticket wird automatisch der Verwaltung von <strong>{geo_match['main_zone']}</strong> zugewiesen.</p>"
            else:
                reply_html += f"<p>⚠️ <strong>Routing-Status:</strong> Territorium außerhalb des POLARIS-Netzwerks.</p>"
                
            # Das HTML bekommt den sauberen Hyperlink
            reply_html += f"<p>🗺️ <a href='{osm_url}' target='_blank'><strong>Punkt auf OpenStreetMap verifizieren</strong></a></p>"
            
            # Text-Fallback für Element-Sicherheit, enthält die URL ebenfalls im Klartext
            text_fallback = (
                f"GeoFence-Fix: {geo_match['main_zone']}. "
                f"Karte: {osm_url}"
            )
            
            await send_encrypted_reply(room_id, text_fallback, reply_html)
            
        except Exception as geo_err:
            print(f"❌ Fehler beim Parsen der GPS-Daten: {geo_err}")
            
async def process_text_message(room_id: str, user_id: str, text: str) -> None:
    text_lower = text.lower()

    # --- 1. ADMIN EXPORT (#export) ---
    if text_lower.startswith("#export"):
        if user_id != ADMIN_USER:
            await send_encrypted_reply(room_id, "❌ Zugriff verweigert: Du hast keine Administrator-Rechte.")
            return
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, "r", encoding="utf-8") as f:
                file_content = f.read()
            reply_html = f"<h3>📊 DB-Export</h3><pre><code>{file_content}</code></pre>"
            await send_encrypted_reply(room_id, file_content, reply_html)
        return

    # --- 2. ABBRUCH-BEFEHL ---
    if text_lower == "abbrechen":
        if user_id in USER_STATES: del USER_STATES[user_id]
        if user_id in HUND_STATES: del HUND_STATES[user_id]
        await send_encrypted_reply(room_id, "❌ Vorgang abgebrochen.")
        return

    # --- 3. DIALOG-STRANG B: HUNDEREGISTER ---
    if user_id in HUND_STATES:
        current_state = HUND_STATES[user_id]
        step = current_state["step"]
        if step == 1:
            if text in ["1", "2", "3", "4"]:
                mapping = {"1": "Golden Retriever / Labrador", "2": "Deutscher Schäferhund", "3": "Pudel / Französische Bulldogge", "4": "Sonstige Rasse / Mischling"}
                current_state["rasse"] = mapping[text]
                current_state["step"] = 2
                await send_encrypted_reply(room_id, "Hundename?", f"<h3>📝 Schritt 2: Name des Hundes</h3><p>Auswahl: <strong>{mapping[text]}</strong>. Bitte tippe nun den Namen des Hundes ein.</p>")
            else:
                await send_encrypted_reply(room_id, "⚠️ Bitte antworte mit 1-4.")
            return
        elif step == 2:
            num = get_next_ticket_id(HUND_CSV)
            meldungs_id = f"#TAX-{datetime.now().strftime('%Y')}-{num:03d}"
            with open(HUND_CSV, mode="a", newline="\n", encoding="utf-8") as f:
                csv.writer(f).writerow([meldungs_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id, room_id, current_state["rasse"], text])
            await send_encrypted_reply(room_id, f"Hund angemeldet: {meldungs_id}", f"<h3>🏛️ Hunderegister-Eintrag erfolgreich!</h3><p>Vorgangs-ID: <strong>{meldungs_id}</strong></p><ul><li>Rasse: {current_state['rasse']}</li><li>Name: {text}</li></ul>")
            del HUND_STATES[user_id]
            return

    # --- 4. DIALOG-STRANG A: SCHADENSMELDUNG ---
    if user_id in USER_STATES:
        current_state = USER_STATES[user_id]
        step = current_state["step"]
        if step == 1:
            if text in ["1", "2", "3", "4"]:
                mapping = {"1": "Schlagloch / Straßenschaden", "2": "Defekte Straßenbeleuchtung", "3": "Wilde Müllkippe", "4": "Sonstiges"}
                current_state["category"] = mapping[text]
                current_state["step"] = 2
                await send_encrypted_reply(room_id, "Ort?", "<h3>📍 Schritt 2: Ort angeben</h3><p>Bitte tippe nun den <strong>Ort oder die Adresse</strong> ein.</p>")
            else:
                await send_encrypted_reply(room_id, "⚠️ Bitte antworte mit 1-4.")
            return
        elif step == 2:
            current_state["location"] = text
            current_state["step"] = 3
            await send_encrypted_reply(room_id, "Details?", "<h3>📝 Schritt 3: Details beschreiben</h3><p>Bitte beschreibe mir nun die <strong>Details</strong> des Schadens.</p>")
            return
        elif step == 3:
            ticket_num = get_next_ticket_id(CSV_FILE)
            ticket_id = f"#CLZ-{datetime.now().strftime('%Y')}-{ticket_num:03d}"
            with open(CSV_FILE, mode="a", newline="\n", encoding="utf-8") as f:
                csv.writer(f).writerow([ticket_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id, room_id, current_state["category"], current_state["location"], text])
            await send_encrypted_reply(room_id, f"Ticket: {ticket_id}", f"<h3>🏛️ Schaden erfasst!</h3><p>Deine Ticket-Nummer lautet: <strong>{ticket_id}</strong>. Verschlüsselt im System hinterlegt. ✅</p>")
            del USER_STATES[user_id]
            return

    # --- BEFEHL-TRIGGER ---
    if text_lower.startswith("#schaden"):
        USER_STATES[user_id] = {"step": 1, "category": "", "location": ""}
        await send_encrypted_reply(room_id, "Schritt 1", "<h3>🏛️ Schadensmelder</h3><p>Wähle die Kategorie (Antworte mit 1, 2, 3 oder 4):</p><ol><li>🕳️ Schlagloch</li><li>💡 Laterne</li><li>🗑️ Müll</li><li>🛠️ Sonstiges</li></ol>")
        return

    if text_lower.startswith("#hund"):
        HUND_STATES[user_id] = {"step": 1, "rasse": "", "name": ""}
        await send_encrypted_reply(room_id, "Hunderegister", "<h3>🐾 Online-Hunderegister</h3><p>Wähle die Rasse (Antworte mit 1, 2, 3 oder 4):</p><ol><li>Retriever/Labrador</li><li>Schäferhund</li><li>Pudel/Bulldogge</li><li>Sonstige/Mischling</li></ol>")
        return

async def send_encrypted_reply(room_id: str, body: str, html: str = None) -> None:
    content = {"msgtype": "m.text", "body": body}
    if html: 
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = html
    try: 
        await client.room_send(room_id=room_id, message_type="m.room.message", content=content, ignore_unverified_devices=True)
    except Exception as e:
        print(f"⚠️ Sende-Fehler: {e}")

async def main() -> None:
    global client
    client = AsyncClient(HOMESERVER, BOT_USER, store_path=STORE_PATH)
    client.encryption_everyone_allowed = False
    
    client.add_event_callback(listen_for_invites, InviteEvent)
    client.add_event_callback(listen_for_events, Event)

    user_id, device_id, access_token = None, None, None
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
                if len(lines) >= 3:
                    user_id = lines[0].strip()
                    device_id = lines[1].strip()
                    access_token = lines[2].strip()
            print("🔑 Token gefunden! Nutze bestehende Geräte-ID...")
        except Exception as e: print(f"⚠️ Credential-Fehler: {e}")

    if user_id and device_id and access_token:
        client.user_id = user_id
        client.device_id = device_id
        client.access_token = access_token
        client.load_store()
        print("🚀 POLARIS-Bot via Token reaktiviert!")
        login_success = True
    else:
        print("🔑 Kein Token vorhanden oder ungültig. Logge einmalig mit Passwort ein...")
        login_response = await client.login(password=BOT_PASSWORD)
        if hasattr(login_response, "access_token"):
            with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                f.write(f"{login_response.user_id}\n{login_response.device_id}\n{login_response.access_token}")
            print("💾 Token für die Zukunft gesichert.")
            login_success = True
        else:
            print(f"❌ Login fehlgeschlagen: {login_response}")
            login_success = False

    if login_success:
        if client.should_upload_keys: await client.keys_upload()
        try:
            print("⚡ Starte Krypto-optimierten Express-Sync-Loop...")
            await client.sync_forever(timeout=30000, full_state=False)
        finally: await client.close()
    else:
        await client.close()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 Bot wurde manuell beendet.")

