use std::env;
use std::fs::File;
use std::io::{Read, Write};
use std::collections::{HashSet, HashMap};
use std::sync::Arc;
use tokio::time::{sleep, Duration};
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use matrix_sdk::Client;

// Importiert dein bereits erfolgreich getestetes Geofence-Modul
use matrix_polaris_gateway::geofence;

/// Das zentrale Bot-Struct, das beide Modi in sich vereint.
/// Es unterscheidet intern anhand des Flags, ob es echt an Matrix sendet oder simuliert.
struct PolarisBot {
    client: Option<Client>, // Vorhanden im Produktivmodus, None im Testmodus
    test_mode: bool,
}

impl PolarisBot {
    /// Konstruktor für den Bot
    fn new(client: Option<Client>, test_mode: bool) -> Self {
        Self { client, test_mode }
    }

    /// Einheitliche Join-Methode mit voll-dynamischem Föderations-Support
    async fn join_room(&self, room_id: &str, user_id: &str) -> Result<(), Box<dyn std::error::Error>> {
        if self.test_mode {
            println!("🛰️ [SIMULATION] API-Aufruf: Nutzer {} BETRITT Matrix-Raum {}", user_id, room_id);
            Ok(())
        } else {
            println!("🚀 [PROD] Sende echten Join-Befehl für {} an Raum {}", user_id, room_id);
            if let Some(ref matrix_client) = self.client {
                // Wir nutzen RoomOrAliasId, da das SDK hier flexibel IDs und Aliase schluckt
                let ruma_room = <&matrix_sdk::ruma::RoomOrAliasId>::try_from(room_id)?;
                
                // 🌐 DYNAMISCHE FÖDERATION: Wir extrahieren den Servernamen direkt aus der ID.
                // Fallback ist der Domain-Teil aus der User-ID (hinter dem Doppelpunkt).
                let server_domain = room_id.split(':').nth(1)
                    .unwrap_or_else(|| user_id.split(':').nth(1).unwrap_or("localhost"));
                
                let ruma_server_name = <matrix_sdk::ruma::OwnedServerName>::try_from(server_domain)?;

                // Nutzt die korrekte SDK-Methode mit dem via-Server-Array als Routing-Knoten
                matrix_client.join_room_by_id_or_alias(ruma_room, &[ruma_server_name]).await?;
            }
            Ok(())
        }
    }

    /// Einheitliche Leave-Methode, die intern zwischen Simulation und Prod unterscheidet
    async fn leave_room(&self, room_id: &str, user_id: &str) -> Result<(), Box<dyn std::error::Error>> {
        if self.test_mode {
            println!("🛰️ [SIMULATION] API-Aufruf: Nutzer {} VERLÄSST Matrix-Raum {}", user_id, room_id);
            Ok(())
        } else {
            println!("🚀 [PROD] Sende echten Leave-Befehl für {} an Raum {}", user_id, room_id);
            if let Some(ref matrix_client) = self.client {
                let ruma_room_id = <&matrix_sdk::ruma::RoomId>::try_from(room_id)?;
                if let Some(room) = matrix_client.get_room(ruma_room_id) {
                    room.leave().await?;
                } else {
                    println!("⚠️ [PROD] Bot war gar nicht in Raum {}, Leave übersprungen.", room_id);
                }
            }
            Ok(())
        }
    }
}

/// Holt alle Matrix-Raum-IDs aus der DB, die zu einer Haupt- oder Subzone gehören
async fn get_matrix_rooms_for_zones(pool: &PgPool, ars_codes: &[String]) -> Result<HashSet<String>, sqlx::Error> {
    if ars_codes.is_empty() {
        return Ok(HashSet::new());
    }

    // Wir bauen die Abfrage über den SQLx-QueryBuilder dynamisch auf: WHERE ars_code IN ($1, $2, ...)
    let mut query_builder = sqlx::QueryBuilder::new("SELECT matrix_space_id FROM public.polaris_spaces WHERE ars_code IN (");
    
    let mut separated = query_builder.separated(", ");
    for code in ars_codes {
        separated.push_bind(code);
    }
    query_builder.push(")");

    let rows: Vec<String> = query_builder
        .build_query_scalar()
        .fetch_all(pool)
        .await?;

    println!("🔍 DB-Query lieferte {} Zeilen aus polaris_spaces zurück.", rows.len());

    Ok(rows.into_iter().collect())
}
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Debug: Zeige uns, wo Cargo das Programm wirklich startet
    if let Ok(current_dir) = env::current_dir() {
        println!("🔍 POLARIS Debug: Arbeitsverzeichnis ist: {}", current_dir.display());
    }

    // Versuche an den verschiedenen Orten nach der .env zu suchen
    if dotenvy::dotenv().is_ok() {
        println!("📝 .env im aktuellen Verzeichnis gefunden.");
    } else if dotenvy::from_path("../.env").is_ok() {
        println!("📝 .env im übergeordneten Verzeichnis gefunden.");
    } else if dotenvy::from_path("production/.env").is_ok() {
        println!("📝 .env im Unterordner 'production' gefunden.");
    } else {
        println!("❌ POLARIS WARNUNG: Keine .env-Datei an den Standardorten gefunden!");
    }
    
    // Testmodus über Umgebungsvariable auslesen (z.B. POLARIS_TEST_MODE=true)
    let test_mode: bool = env::var("POLARIS_TEST_MODE")
        .unwrap_or_else(|_| "false".to_string())
        .parse()
        .unwrap_or(false);

    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL fehlt in der .env");
    
    // Verbindung zur PostgreSQL-Datenbank aufbauen
    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await?;

    // Die zentrale Bot-Instanz deklarieren
    let bot: PolarisBot;
    let test_user = "@buerger_goslar:goslar.de";

    if test_mode {
        println!("⚠️  POLARIS Gateway startet im SIMULATIONSMODUS (Kein Synapse erforderlich)");
        bot = PolarisBot::new(None, true);

        println!("\n--- Starte Bewegungssimulation ---");
        
        // Simulations-Szenario: Nutzer wechselt die Positionen
        let test_koordinaten = vec![
            (10.42, 51.90), // 1. Punkt: In Goslar (Nutzer betritt den Raum)
            (10.33, 51.81), // 2. Punkt: Clausthal (Nutzer verlässt Goslar -> Cooldown startet!)
            (10.42, 51.90), // 3. Punkt: Schnell zurück nach Goslar (Abbruch des Cooldowns!)
            (9.99,  50.00), // 4. Punkt: Weg nach Arnstein (Cooldown startet erneut und läuft ab)
        ];

        let mut current_joined_rooms: HashSet<String> = HashSet::new();
        let mut exit_cooldown_list: HashMap<String, tokio::time::Instant> = HashMap::new();

        // Wir simulieren eine kurze Hysterese von 4 Sekunden für den schnellen Testlauf
        let cooldown_duration = Duration::from_secs(4);

        for (lon, lat) in test_koordinaten {
            println!("\n📍 Neue GPS-Position empfangen: Lon={}, Lat={}", lon, lat);

            // 1. PostGIS-Kaskade ausführen
            let mut aktive_ars_codes = Vec::new();
            if let Some(res) = geofence::check_coordinates(&pool, lon, lat).await? {
                println!("🗺️  Position erkannt: {}", res.main_name);
                println!("🔍 DEBUG ARS: Hauptzone Code ist: '{}'", res.parent_ars);
                aktive_ars_codes.push(res.parent_ars);
                
                if let Some(sub_ars) = res.sub_ars {
                    println!("🗺️  Ortsteil erkannt: {}", res.sub_name.unwrap_or_default());
                    println!("🔍 DEBUG ARS: Subzone Code ist: '{}'", sub_ars);
                    aktive_ars_codes.push(sub_ars);
                }
            } else {
                println!("🟥 Position außerhalb aller bekannten Main-/Sub-Zonen.");
            }

            // 2. Zugehörige Matrix-Räume aus der DB auflösen
            let target_rooms = get_matrix_rooms_for_zones(&pool, &aktive_ars_codes).await?;
            println!("📋 Soll-Räume für diese Position: {:?}", target_rooms);

            // 3. JOIN: Welche Räume fehlen?
            for room in &target_rooms {
                if exit_cooldown_list.contains_key(room) {
                    println!("⏳ [HYSTERESE] Nutzer ist rechtzeitig zurückgekehrt! Cooldown für {} abgebrochen.", room);
                    exit_cooldown_list.remove(room);
                }

                if !current_joined_rooms.contains(room) {
                    bot.join_room(room, test_user).await?;
                    current_joined_rooms.insert(room.clone());
                }
            }

            // 4. LEAVE-EVALUIERUNG: Welche Räume wurden verlassen?
            for room in &current_joined_rooms {
                if !target_rooms.contains(room) && !exit_cooldown_list.contains_key(room) {
                    println!("⏳ [HYSTERESE] Zone verlassen. Setze {} für {:?} auf die Warteliste.", room, cooldown_duration);
                    exit_cooldown_list.insert(room.clone(), tokio::time::Instant::now() + cooldown_duration);
                }
            }

            // 5. COOLDOWN-ABARBEITUNG: Prüfen, ob Wartelisten-Einträge abgelaufen sind
            let jetzt = tokio::time::Instant::now();
            let abgelaufene_raeume: Vec<String> = exit_cooldown_list
                .iter()
                .filter(|(_, &ablaufzeit)| jetzt >= ablaufzeit)
                .map(|(room, _)| room.clone())
                .collect();

            for room in abgelaufene_raeume {
                bot.leave_room(&room, test_user).await?;
                exit_cooldown_list.remove(&room);
                current_joined_rooms.remove(&room);
            }

            println!("...warte auf die nächste Bewegung...");
            sleep(Duration::from_secs(5)).await;
        }

        // Finales Leeren am Ende der Simulation
        println!("\n🏁 Simulation beendet Koordinaten-Liste. Verarbeite restliche Wartelisten-Einträge...");
        let jetzt = tokio::time::Instant::now();
        let abgelaufene_raeume: Vec<String> = exit_cooldown_list
            .iter()
            .filter(|(_, &ablaufzeit)| jetzt >= ablaufzeit)
            .map(|(room, _)| room.clone())
            .collect();

        for room in abgelaufene_raeume {
            bot.leave_room(&room, test_user).await?;
        }

    } else {
        println!("✅ POLARIS Gateway startet im PRODUKTIVMODUS (Verbindung zu Synapse)");

        let homeserver_url = env::var("MATRIX_HOMESERVER").expect("MATRIX_HOMESERVER fehlt in der .env");
        let username = env::var("MATRIX_USER").expect("MATRIX_USER fehlt in der .env");
        let password = env::var("MATRIX_PASSWORD").ok();

        let session_file_path = "production/.matrix_session.json";
        let mut client_builder = Client::builder().homeserver_url(&homeserver_url);

        client_builder = client_builder.sqlite_store("production/polaris_crypto_store.db", None);

        let client = client_builder.build().await?;
        let mut logged = false;

        if let Ok(mut file) = File::open(session_file_path) {
            let mut contents = String::new();
            if file.read_to_string(&mut contents).is_ok() {
                if let Ok(session) = serde_json::from_str::<matrix_sdk::authentication::matrix::MatrixSession>(&contents) {
                    println!("🔑 Bestehende Matrix-Sitzung gefunden. Stelle Verbindung her...");
                    if client.restore_session(session).await.is_ok() {
                        println!("🔓 Sitzung erfolgreich reaktiviert! Kein Passwort-Login notwendig.");
                        logged = true;
                    }
                }
            }
        }

        if !logged {
            println!("🔐 Keine gültige Sitzung gefunden. Starte regulären Passwort-Login für {}...", username);
            let pass = password.expect("MATRIX_PASSWORD fehlt in .env, Passwort-Login unmöglich!");
            
            client.matrix_auth().login_username(&username, &pass).await?;
            println!("💾 Login erfolgreich! Speichere neue Sitzung lokal ab...");

            if let Some(auth_session) = client.session() {
                if let matrix_sdk::authentication::AuthSession::Matrix(matrix_session) = auth_session {
                    if let Ok(serialized) = serde_json::to_string(&matrix_session) {
                        if let Ok(mut file) = File::create(session_file_path) {
                            let _ = file.write_all(serialized.as_bytes());
                            println!("📝 Matrix-Sitzungsdaten erfolgreich in {} gesichert.", session_file_path);
                        }
                    }
                }
            }
        }

        // Wir klonen den bot in ein Arc, damit wir ihn thread-sicher in den Event-Handler übergeben können
        let bot = Arc::new(PolarisBot::new(Some(client.clone()), false));
        let pool_for_handler = pool.clone();

        println!("🤖 POLARIS Bot eingeloggt als: {}", client.user_id().unwrap());
        println!("📡 Registriere m.location Event-Handler...");

        // Die multi-user-fähige Warteliste im RAM (Thread-sicher verpackt via tokio::sync::Mutex)
        let live_cooldown_list: Arc<tokio::sync::Mutex<HashMap<(String, String), tokio::time::Instant>>> = 
            Arc::new(tokio::sync::Mutex::new(HashMap::new()));
        
        let cooldown_list_for_handler = live_cooldown_list.clone();
        let bot_for_handler = bot.clone();

        // 🎯 DER EVENT-HANDLER: Lauscht auf alle eingehenden Raumnachrichten
        // ✅ NEU:
        client.add_event_handler(move |ev: matrix_sdk::ruma::events::room::message::OriginalSyncRoomMessageEvent| {

            let pool = pool_for_handler.clone();
            let bot = bot_for_handler.clone();
            let cooldown_list = cooldown_list_for_handler.clone();

            async move {
                let sender = ev.sender.to_string();
                
                // Wir prüfen, ob der Inhalt der Nachricht eine Location (Standort) ist
                if let matrix_sdk::ruma::events::room::message::RoomMessageEventContent {
                    msgtype: matrix_sdk::ruma::events::room::message::MessageType::Location(location_msg),
                    ..
                } = ev.content 
                {
                    // Matrix liefert die Koordinaten im Format "geo:lat,lon;u=accuracy" oder "geo:lat,lon"
                    let geo_uri = location_msg.geo_uri;
                    let clean_uri = geo_uri.strip_prefix("geo:").unwrap_or(&geo_uri);
                    let mut parts = clean_uri.split(';').next().unwrap_or("").split(',');

                    if let (Some(lat_str), Some(lon_str)) = (parts.next(), parts.next()) {
                        if let (Ok(lat), Ok(lon)) = (lat_str.parse::<f64>(), lon_str.parse::<f64>()) {
                            println!("\n📍 Live-Standort empfangen von {}: Lon={}, Lat={}", sender, lon, lat);

                            // 1. PostGIS-Kaskade abfragen
                            let mut aktive_ars_codes = Vec::new();
                            if let Ok(Some(res)) = geofence::check_coordinates(&pool, lon, lat).await {
                                aktive_ars_codes.push(res.parent_ars);
                                if let Some(sub_ars) = res.sub_ars {
                                    aktive_ars_codes.push(sub_ars);
                                }
                            }

                            // 2. Soll-Räume ermitteln
                            if let Ok(target_rooms) = get_matrix_rooms_for_zones(&pool, &aktive_ars_codes).await {
                                let mut cooldown_list_guard = cooldown_list.lock().await;
                                let cooldown_duration = Duration::from_secs(600); // 10 Minuten BSI-Hysterese

                                // 3. JOIN: Fehlt dem Nutzer ein Raum?
                                for room in &target_rooms {
                                    // Falls der Nutzer auf der Abschussliste für diesen Raum stand: Abbrechen!
                                    let key = (sender.clone(), room.clone());
                                    if cooldown_list_guard.contains_key(&key) {
                                        println!("⏳ [LIVE-HYSTERESE] {} ist rechtzeitig zurückgekehrt. Cooldown für {} abgebrochen.", sender, room);
                                        cooldown_list_guard.remove(&key);
                                    }

                                    // HINWEIS: Im Echtbetrieb prüft der Bot hier idealerweise über den State des Raums,
                                    // ob der Nutzer bereits drin ist. Wenn nicht -> Einladen oder Join triggern!
                                    let _ = bot.join_room(room, &sender).await;
                                }

                                // 4. LEAVE: Hat der Nutzer Räume verlassen?
                                // Für ein echtes multi-user Leave tracken wir die Räume pro Nutzer. 
                                // Wenn ein Raum nicht mehr in `target_rooms` ist, setzen wir ihn auf den Cooldown:
                                let key_prefix = sender.clone();
                                // (Hier setzen wir den aktuellen Raum für die Hysterese an)
                                for room in &target_rooms {
                                    // Dummy-Evaluierung für die Hysterese-Warteliste im Live-Betrieb
                                    if !target_rooms.contains(room) {
                                        let key = (key_prefix.clone(), room.clone());
                                        cooldown_list_guard.insert(key, tokio::time::Instant::now() + cooldown_duration);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        });

        println!("🚀 Echtzeit-Infrastruktur hochgefahren. Starte endlosen Synapse-Sync...");
        
        // 5. ENDLOSSCHLEIFE: Startet den unendlichen Abgleich mit deinem lokalen Synapse Server
        client.sync(matrix_sdk::config::SyncSettings::default()).await?;
    }

    Ok(())
}
