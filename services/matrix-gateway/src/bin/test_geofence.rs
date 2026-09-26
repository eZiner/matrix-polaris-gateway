use clap::Parser;
use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use std::env;

// Binde das Bibliotheksmodul ein
// Ersetze 'matrix_polaris_gateway' durch das Paket aus deiner Cargo.toml
use matrix_polaris_gateway::geofence;

#[derive(Parser, Debug)]
struct Args {
    #[arg(long)]
    lon: f64,
    #[arg(long)]
    lat: f64,
}

// Das ist der Einstiegspunkt für die Ausführung!
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    dotenv().ok();
    let args = Args::parse();

    println!("📍 Teste Koordinate: Lon={}, Lat={}", args.lon, args.lat);

    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL fehlt");

    let pool = PgPoolOptions::new()
        .max_connections(2)
        .connect(&database_url)
        .await?;

    match geofence::check_coordinates(&pool, args.lon, args.lat).await? {
        Some(res) => {
            println!("🟩 Gemeinde: {} (ARS: {})", res.main_name, res.parent_ars);
            if let (Some(sub_ars), Some(sub_name)) = (res.sub_ars, res.sub_name) {
                println!("🟦 Ortsteil: {} (ID: {})", sub_name, sub_ars);
            }
        }
        None => println!("🟥 Außerhalb der Zonen."),
    }

    Ok(())
}
