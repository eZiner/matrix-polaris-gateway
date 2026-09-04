use std::env;
use std::collections::HashSet;
use std::sync::Arc;
use std::time::{Duration, Instant};
use dashmap::DashMap;
use matrix_sdk::{
    config::SyncSettings, // <-- DIESE ZEILE HIER HINZUFÜGEN!
    room::Room,
    ruma::{
        events::room::message::{MessageType, OriginalSyncRoomMessageEvent},
        OwnedRoomId, OwnedUserId, RoomId, UserId,
    },
    Client,
};
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use tracing::{error, info, Level};
use tracing_subscriber::FmtSubscriber;

// --- SOUVERÄNE ARCHITEKTUR-KONSTANTEN ---
const HOMESERVER_URL: &str = "https://goslar.de"; // Physisch im Uni-Rechenzentrum
const BOT_USER_ID: &str = "@polaris-gateway:goslar.de";
const BOT_PASSWORD: &str = "DeinStrengGeheimesBotPasswortHier";

// Das exklusive, vordefinierte Chatfenster NUR für den Geo-Fencing-Bot
const GEOFENCING_BOT_ROOM_ID: &str = "!vordefinierterBotRaumID:goslar.de";

// Hysterese-Schutz Konfiguration (10 Minuten Cooldown)
const COOLDOWN_DURATION: Duration = Duration::from_secs(600);

// --- IN-MEMORY RAM SPEICHER (Flüchtig via DashMap für thread-sicheren Parallelzugriff) ---
struct GlobalState {
    db_pool: PgPool,
    // Struktur: { user_id: HashSet<space_id> }
    active_user_spaces: DashMap<OwnedUserId, HashSet<OwnedRoomId>>,
    // Struktur: { (user_id, space_id): Instant_when_outside }
    exit_pending_users: DashMap<(OwnedUserId, OwnedRoomId), Instant>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 1. Holt die Variable live aus dem Betriebssystem-Speicher
    let database_url = env::var("DATABASE_URL")
        .expect("❌ FEHLER: Die Umgebungsvariable 'DATABASE_URL' ist nicht gesetzt!");

    // Logging initialisieren
    let subscriber = FmtSubscriber::builder().with_max_level(Level::INFO).finish();
    tracing::subscriber::set_global_default(subscriber)?;

    info!("Verbinde mit der lokalen PostGIS-Datenbank...");
    let db_pool  = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url) // Nutzt die dynamische Variable aus deiner .env!
        .await?;

    // Globalen, flüchtigen RAM-Zustand aufbauen
    let state = Arc::new(GlobalState {
        db_pool,
        active_user_spaces: DashMap::new(),
        exit_pending_users: DashMap::new(),
    });

    info!("Verbinde mit dem universitären Kommunal-Homeserver...");
    let bot_id = <&UserId>::try_from(BOT_USER_ID)?;
    let client = Client::builder()
        .homeserver_url(HOMESERVER_URL)
        .build()
        .await?;

    client.matrix_auth().login_username(bot_id, BOT_PASSWORD).await?;
    info!("Bot erfolgreich eingeloggt.");

    // Hysterese-Hintergrund-Thread für den automatisierten Server-Kick starten
    let loop_client = client.clone();
    let loop_state = state.clone();
    tokio::spawn(async move {
        cooldown_cleanup_loop(loop_client, loop_state).await;
    });

    // Event-Handler für eingehende Nachrichten registrieren
    let handler_state = state.clone();
    client.add_event_handler(
        move |event: OriginalSyncRoomMessageEvent, room: Room, client: Client| {
            let state = handler_state.clone();
            async move {
                if let Err(e) = message_callback(event, room, client, state).await {
                    error!("Fehler im Event-Handler: {:?}", e);
                }
            }
        },
    );
    // Asynchrone Sync-Schleife des Matrix-Protokolls starten
    info!("POLARIS-Gateway aktiv. Lausche im vordefinierten Bot-Raum...");
    let sync_settings = SyncSettings::default();
    client.sync(sync_settings).await?;

    Ok(())
}

async fn check_geofencing_postgis(pool: &PgPool, lon: f64, lat: f64) -> Result<HashSet<OwnedRoomId>, sqlx::Error> {
    // Die exakte Koordinate wird nach der Query im RAM nicht persistiert
    let rows = sqlx::query!(
        "SELECT matrix_space_id FROM polaris_infospaces \
         WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326));",
        lon, lat
    )
    .fetch_all(pool)
    .await?;

    let mut spaces = HashSet::new();
    for row in rows {
        if let Ok(room_id) = RoomId::parse(row.matrix_space_id) {
            spaces.insert(room_id);
        }
    }
    Ok(spaces)
}

async fn message_callback(
    event: OriginalSyncRoomMessageEvent,
    room: Room,
    client: Client,
    state: Arc<GlobalState>,
) -> anyhow::Result<()> {
    // STRIKTE FILTERUNG: Reagiere ausschließlich im vordefinierten Bot-Raum
    if room.room_id() != <&RoomId>::try_from(GEOFENCING_BOT_ROOM_ID)? {
        return Ok(());
    }

    // Ignoriere eigene Nachrichten des Bots
    if event.sender == client.user_id().unwrap() {
        return Ok(());
    }

    // Prüfen auf standardisierte m.location-Events innerhalb des Nachrichteninhalts
    if let MessageType::Location(location_content) = &event.content.msgtype {
        let geo_uri = &location_content.geo_uri; // Format: "geo:51.9059;10.4292"
        
        // Extraktion der Koordinaten flüchtig in lokale RAM-Variablen
        if let Some(coords_str) = geo_uri.strip_prefix("geo:") {
            let parts: Vec<&str> = coords_str.split(';').next().unwrap_or("").split(',').collect();
            if parts.len() == 2 {
                let lat: f64 = parts[0].parse()?;
                let lon: f64 = parts[1].parse()?;
                
                let user_id = event.sender.clone();
                info!("Standort-Signal von {} empfangen. Starte flüchtigen RAM-Abgleich...", user_id);

                // 1. PostGIS-Abfrage ausführen
                let matched_spaces = check_geofencing_postgis(&state.db_pool, lon, lat).await?;

                // User-Eintrag in der flüchtigen DashMap sicherstellen
                state.active_user_spaces.entry(user_id.clone()).or_insert_with(HashSet::new);

                // 2. EVALUIERUNG: NEUE INFO-SPACES BETRETEN (Geräuschloser Auto-Join)
                for space_id in &matched_spaces {
                    let mut current_spaces = state.active_user_spaces.get_mut(&user_id).unwrap();
                    
                    if !current_spaces.contains(space_id) {
                        let cache_key = (user_id.clone(), space_id.clone());
                        
                        // Falls im Cooldown, brich den Exit ab (Re-Entry)
                        if state.exit_pending_users.contains_key(&cache_key) {
                            state.exit_pending_users.remove(&cache_key);
                            info!("Hysterese abgebrochen für {} in {} (Re-Entry).", user_id, space_id);
                        } else {
                            // Nativer, geräuschloser Server-Beitritt via Föderation über Port 8448
                            if let Some(target_room) = client.get_room(space_id) {
                                target_room.join().await?;
                                current_spaces.insert(space_id.clone());
                                info!("Geräuschloser Auto-Join ausgeführt: {} -> Infospace {}", user_id, space_id);
                            }
                        }
                    }
                }

                // 3. EVALUIERUNG: SPACES VERLASSEN (Hysterese-Warteliste)
                let current_spaces = state.active_user_spaces.get_mut(&user_id).unwrap();
                for current_space_id in current_spaces.clone() {
                    if !matched_spaces.contains(&current_space_id) {
                        let cache_key = (user_id.clone(), current_space_id.clone());
                        if !state.exit_pending_users.contains_key(&cache_key) {
                            state.exit_pending_users.insert(cache_key, Instant::now());
                            info!("User {} hat Zone verlassen. Setze {} auf Cooldown-Liste.", user_id, current_space_id);
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

async fn cooldown_cleanup_loop(client: Client, state: Arc<GlobalState>) {
    loop {
        tokio::time::sleep(Duration::from_secs(10)).await; // Alle 10 Sekunden prüfen
        let now = Instant::now();

        // Iteriere über alle wartenden Exits
        let pending_exits: Vec<((OwnedUserId, OwnedRoomId), Instant)> = state
            .exit_pending_users
            .iter()
            .map(|r| (r.key().clone(), *r.value()))
            .collect();

        for (key, timestamp) in pending_exits {
            // Wenn der 10-Minuten-Cooldown abgelaufen ist
            if now.duration_since(timestamp) >= COOLDOWN_DURATION {
                let (user_id, space_id) = key.clone();
                
                if let Some(target_room) = client.get_room(&space_id) {
                    // Automatisierter Server-Kick aus dem gesamten Infospace-Container
                    let reason = "Zone dauerhaft verlassen (Datenhygiene).";
                    // Prüfen, ob wir in dem Raum überhaupt aktiv drin sind, um jemanden kicken zu können
                    if let Err(e) = target_room.kick_user(&user_id, Some(&reason)).await {
                        eprintln!("❌ Fehler beim Kicken des Users {}: {:?}", user_id, e);
                    }
                    // Aus dem flüchtigen RAM-Speicher löschen
                    if let Some(mut user_spaces) = state.active_user_spaces.get_mut(&user_id) {
                        user_spaces.remove(&space_id);
                    }
                    state.exit_pending_users.remove(&key);
                    info!("Datenhygiene erfolgreich: {} aus Infospace {} entfernt.", user_id, space_id);
                }
            }
        }
    }
}