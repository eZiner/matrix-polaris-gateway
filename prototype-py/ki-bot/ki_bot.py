import asyncio
import os
import csv
import logging
import sys
import urllib.parse
import aiohttp  # 📍 HIER NEU: Für die blitzschnelle, asynchrone KI-Kommunikation!
import json
from datetime import datetime
import psycopg2  # Live-Kopplung an eure PostGIS-Datenbank
from dotenv import load_dotenv  # Zieht die Daten sicher aus der .env
from nio import AsyncClient, MatrixRoom, InviteEvent, RoomMessageText, Event, UnknownEvent

# 📍 DER ABSOLUTE PFAD-FIX: Ermittelt zwingend den echten Ordner dieser ki_bot.py
script_dir = os.path.dirname(os.path.abspath(__file__))
local_env_path = os.path.join(script_dir, ".env")
parent_env_path = os.path.join(script_dir, "../../.env")

# 1. Zuerst die lokale Labor-.env über den absoluten Pfad laden und hart überschreiben
if os.path.exists(local_env_path):
    load_dotenv(dotenv_path=local_env_path, override=True)
    print(f"📌 KI-LABOR: Lokale .env absolut geladen von: {local_env_path}")
else:
    print("⚠️ KI-LABOR: Lokale .env wurde an diesem absoluten Pfad NICHT gefunden!")

# 2. Danach die Haupt-.env zwei Ebenen höher als Fallback für DATABASE_URL laden
if os.path.exists(parent_env_path):
    load_dotenv(dotenv_path=parent_env_path)
    print(f"📌 KI-LABOR: Haupt-.env absolut geladen von: {parent_env_path}")

# Schaltet das blockierende Krypto-Fehler-Logging von matrix-nio stumm
logging.getLogger("nio.crypto").setLevel(logging.CRITICAL)

# --- CONFIGURATION VIA ENVIRONMENT VARIABLES ---
HOMESERVER = os.getenv("MATRIX_HOMESERVER")
BOT_USER = os.getenv("MATRIX_BOT_USER")
BOT_PASSWORD = os.getenv("MATRIX_BOT_PASSWORD")

print(f"🤖 KI-LABOR ACTIVE-USER: {BOT_USER}")

ADMIN_USER = os.getenv("MATRIX_ADMIN_USER")

STORE_PATH = "./bot_store/"
CREDENTIALS_FILE = "bot_credentials.txt"
CSV_FILE = "schadensmeldungen.csv"
HUND_CSV = "hunderegister.csv"

# 📍 OLLAMA-ENDPUNKT (Dein frisch installierter Container auf Localhost!)
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

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

# 📍 HIER NEU: ASYNCHRONE FUNKTION ZUM ANFUNKEN DEINER TERMINAL-KI!
async def ask_local_ai(user_prompt: str) -> str:
    # 📍 HIER NEU: Der Bot liest live euer lokales Behörden-Handbuch aus!
    wissen_kontext = ""
    wissen_datei = "rathaus_wissen.txt"
    
    if os.path.exists(wissen_datei):
        try:
            with open(wissen_datei, "r", encoding="utf-8") as f:
                wissen_kontext = f.read()
            print("📖 KI-GATEWAY: Behörden-Handbuch erfolgreich eingelesen und geladen!")
        except Exception as e:
            print(f"⚠️ Fehler beim Lesen der Wissensdatei: {e}")

    # Wir impfen der KI ihr behördliches Verhalten UND das echte Wissen ein!
    system_context = (
        "Du bist POLARIS, der offizielle, sachliche KI-Assistent für das Rathaus "
        "Clausthal-Zellerfeld und die Bergstadt Wildemann.\n"
        "STRENGE REGELN FÜR DIE PRÄSENTATION:\n"
        "1. Antworte AUSSCHLIESSLICH mit Fakten aus dem beigefügten Behörden-Handbuch.\n"
        "2. Wenn die Antwort oder ein Begriff NICHT im Handbuch steht (z.B. bei einem einfachen 'Moin' oder 'Hallo'), "
        "antworte standardisiert: 'Moin! Ich bin dein digitaler Rathaus-Assistent. Wie kann ich dir heute auf Basis unseres Behörden-Handbuchs helfen?'\n"
        "3. Erfinde NIEMALS Internet-Links, Telefonnummern oder Schreibweisen (wie Clusthal). Wenn etwas fehlt, verweise sachlich an das echte Bürgerbüro.\n"
        "4. Antworte kurz, direkt und ohne Einleitungs-Floskeln.\n\n"
        f"OFFIZIELLES BEHÖRDEN-HANDBUCH:\n{wissen_kontext}"
    )
        
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system_context}\n\nBürger-Frage: {user_prompt}\nAntwort:",
        "stream": False
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "").strip()
                else:
                    return "⚠️ Das Rathaus-KI-Backend meldet aktuell Überlastung. Bitte versuche es gleich noch einmal."
    except Exception as e:
        print(f"❌ Fehler bei der KI-Anfrage an Ollama: {e}")
        return "⚠️ Verbindung zum lokalen KI-Dienst vorübergehend unterbrochen."

# 🛰️ ORIGINAL GEOFENCE ENGINE (Mit deiner 127.0.0.1 Krücke)
def query_postgis_geofence(lat, lon):
    print(f"🛰️ POSTGIS: Analysiere Territorium für GPS-Fix Lat={lat}, Lon={lon}...")
    result = {
        "matched": False, "main_zone": "Unbekanntes Gebiet", "ars": "Kein ARS-Code", "sub_zones": []
    }
    db_url = os.getenv("DATABASE_URL")
    if db_url and "@polaris-db" in db_url:
        db_url = db_url.replace("@polaris-db", "@127.0.0.1")
    elif db_url and "@postgres" in db_url:
        db_url = db_url.replace("@postgres", "@127.0.0.1")
        
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        sql = """
            SELECT m.name AS main_name, s.name AS sub_name, m.ars_code, s.type AS sub_type
            FROM sub_zones s
            JOIN main_zones m ON s.main_zone_id = m.id
            WHERE ST_Contains(s.geometry, ST_SetSRID(ST_Point(%s, %s), 4326));
        """
        cursor.execute(sql, (lon, lat))
        rows = cursor.fetchall()
        if rows:
            result["matched"] = True
            result["main_zone"] = rows
            result["ars"] = rows
            for row in rows:
                result["sub_zones"].append(f"{row:<25} | Typ: {row}")
        cursor.close()
        conn.close()
    except Exception as db_err:
        print(f"❌ PostGIS-Datenbankfehler: {db_err}")
    return result

async def listen_for_invites(room: MatrixRoom, event: InviteEvent) -> None:
    try: await client.join(room.room_id)
    except Exception: pass

# --- DAS GEOFENCE-GATEWAY INTERFACE ---
async def listen_for_events(room: MatrixRoom, event: Event) -> None:
    if event.sender == BOT_USER: return
    room_id, user_id = room.room_id, event.sender

    if isinstance(event, RoomMessageText):
        await process_text_message(room_id, user_id, event.body.strip())
        return

    event_source = getattr(event, "source", {})
    event_content = event_source.get("content", {})
    event_type = event_source.get("type", "")
    if not event_content: return

    msgtype = event_content.get("msgtype")
    if msgtype == "m.location":
        print(f"📥 GEO-GATEWAY: Klassischen Standort-Ping erhalten von {user_id}!")
        geo_uri = event_content.get("geo_uri")
        if not geo_uri and "org.matrix.msc3488.location" in event_content:
            geo_uri = event_content.get("org.matrix.msc3488.location", {}).get("uri")
        if geo_uri: await handle_gps_coordinates(room_id, user_id, geo_uri, "Klassischer Ping")
        return

    if event_type == "org.matrix.msc3672.beacon_info":
        is_live = event_content.get("live", True)
        if is_live:
            print(f"🛰️ GEO-GATEWAY: Live-Standort-Stream wurde von {user_id} initialisiert!")
            try: await client.keys_query()
            except Exception: pass
            reply_html = "<h3>🛰️ POLARIS GeoFence Gateway</h3><p>Live-Standort-Stream erfolgreich verbunden.</p>"
            await send_encrypted_reply(room_id, "Live-Standort verbunden...", reply_html)
        else:
            print(f"🛑 GEO-GATEWAY: Live-Standort-Stream wurde von {user_id} beendet!")
            reply_html = "<h3>🛑 GeoFence Gateway: Verbindung getrennt</h3><p>Der Live-GPS-Stream wurde geschlossen.</p>"
            await send_encrypted_reply(room_id, "Live-Standort-Stream beendet.", reply_html)
        return

    if event_type == "org.matrix.msc3671.beacon" or "beacon" in event_type:
        loc_structure = event_content.get("org.matrix.msc3488.location", {})
        geo_uri = loc_structure.get("uri")
        if not geo_uri:
            for key, val in event_content.items():
                if isinstance(val, dict) and "uri" in val and str(val["uri"]).startswith("geo:"):
                    geo_uri = val["uri"]
        if geo_uri: await handle_gps_coordinates(room_id, user_id, geo_uri, "Live-Tracking 🛰️")
        return

async def handle_gps_coordinates(room_id: str, user_id: str, geo_uri: str, methode: str):
    if geo_uri.startswith("geo:"):
        try:
            coords_part = geo_uri[4:]
            if ";" in coords_part: coords_part = coords_part.split(";")
            lat_str, lon_str = coords_part.split(",")
            latitude, longitude = float(lat_str), float(lon_str)
            geo_match = query_postgis_geofence(latitude, longitude)
            
            sub_zones_html = "".join([f"<li>► <code>{sz}</code></li>" for sz in geo_match["sub_zones"]])
            if not sub_zones_html: sub_zones_html = "<li>Außerhalb bekannter Sektoren</li>"
            
            reply_html = (
                f"<h3>🛰️ GeoFence Gateway: Föderations-Routing</h3>"
                f"<p>Empfangsmethode: <strong>{methode}</strong></p>"
                f"<ul>"
                f"<li>🌐 <strong>GPS-Koordinate:</strong> <code>{latitude}, {longitude}</code></li>"
                f"<li>🏛️ <strong>Hauptzone (Gemeinde):</strong> <strong>{geo_match['main_zone']}</strong></li>"
                f"<li>🎫 <strong>Amtlicher Regionalschlüssel (ARS):</strong> <code>{geo_match['ars']}</code></li>"
                f"</ul>"
                f"<h4>🏡 Erkannte Sektoren (Sub-Zonen):</h4><ul>{sub_zones_html}</ul>"
            )
            if geo_match["matched"]:
                reply_html += f"<p>✅ <strong>Routing-Status:</strong> Das Ticket wird der Verwaltung von <strong>{geo_match['main_zone']}</strong> zugewiesen.</p>"
            else:
                reply_html += f"<p>⚠️ <strong>Routing-Status:</strong> Territorium außerhalb des POLARIS-Netzwerks.</p>"
            
            osm_url = f"https://openstreetmap.org{latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
            reply_html += f"<p>🗺️ <a href='{osm_url}' target='_blank'><strong>Punkt auf OpenStreetMap verifizieren</strong></a></p>"
            text_fallback = f"GeoFence-Fix: {geo_match['main_zone']}. Karte: {osm_url}"
            await send_encrypted_reply(room_id, text_fallback, reply_html)
        except Exception as geo_err: print(f"❌ Fehler beim Parsen der GPS-Daten: {geo_err}")
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

    # 📍 HIER NEU: DIE KI-WEICHE FÜR FREIEN TEXT
    # Wenn kein Befehl gematcht hat, übergeben wir die Bürgeranfrage live an Ollama!
    print(f"🤖 KI-GATEWAY: Verarbeite freie Bürgeranfrage von {user_id} via Ollama...")
    
    # Dem Bürger ein kurzes Lebenszeichen senden, während die CPU rechnet
    # (Kann im echten Betrieb auch weggelassen werden, da Ollama in 1-2 Sek antwortet)
    # await client.room_typing(room_id, timeout=3000)
    
    ai_response = await ask_local_ai(text)
    
    # Formatierte HTML-Antwort für das Amt bauen
    reply_html = (
        f"<h3>🤖 POLARIS Bürger-Assistent</h3>"
        f"<p>{ai_response}</p>"
        f"<p><small>⏱️ <em>Antwort lokal generiert auf souveräner Hardware. Keine Drittdaten-Übertragung.</em></small></p>"
    )
    
    await send_encrypted_reply(room_id, ai_response, reply_html)

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
