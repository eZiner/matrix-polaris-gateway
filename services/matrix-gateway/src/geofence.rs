use sqlx::PgPool;

/// Struktur für das Ergebnis der Geofencing-Abfrage
#[derive(Debug)]
pub struct GeofenceResult {
    pub parent_ars: String,
    pub main_name: String,
    pub sub_ars: Option<String>,
    pub sub_name: Option<String>,
}

/// Führt die zweistufige PostGIS-Kaskade aus (BKG-Gemeinde -> OSM-Ortsteil)
pub async fn check_coordinates(
    pool: &PgPool,
    lon: f64,
    lat: f64,
) -> Result<Option<GeofenceResult>, sqlx::Error> {
    // Stufe 1: Hauptzone (Gemeinde) ermitteln
    let main_zone_query = r#"
        SELECT ars_code, zone_name 
        FROM public.main_zones 
        WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint($1, $2), 4326));
    "#;

    let main_zone: Option<(String, String)> = sqlx::query_as(main_zone_query)
        .bind(lon)
        .bind(lat)
        .fetch_optional(pool)
        .await?;

    if let Some((parent_ars, main_name)) = main_zone {
        // Stufe 2: Gezielter Drilldown in die Subzonen dieser Gemeinde
        let sub_zone_query = r#"
            SELECT ars_code, zone_name 
            FROM public.sub_zones 
            WHERE parent_ars = $1 
              AND ST_Contains(geometry, ST_SetSRID(ST_MakePoint($2, $3), 4326));
        "#;

        let sub_zone: Option<(String, String)> = sqlx::query_as(sub_zone_query)
            .bind(&parent_ars)
            .bind(lon)
            .bind(lat)
            .fetch_optional(pool)
            .await?;

        if let Some((sub_ars, sub_name)) = sub_zone {
            Ok(Some(GeofenceResult {
                parent_ars,
                main_name,
                sub_ars: Some(sub_ars),
                sub_name: Some(sub_name),
            }))
        } else {
            Ok(Some(GeofenceResult {
                parent_ars,
                main_name,
                sub_ars: None,
                sub_name: None,
            }))
        }
    } else {
        Ok(None)
    }
}
