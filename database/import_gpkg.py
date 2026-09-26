#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLARIS INFRASTRUCTURE PIPELINE - BKG BASE IMPORTER
Hebt die offiziellen Verwaltungsgrenzen (VG25) in die Tabelle 'main_zones'.
Zeitstempel: Samstag, 12. September 2026
Lizenz: Public Domain / CC0 (Gemeinfrei)
"""

import os
import sys
import psycopg2
import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine

def main():
    print("🚀 POLARIS BKG-Importer v2.0.0 wird gestartet...")

    # 1. Dynamische Pfad-Auflösung für die .env-Datei
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(os.path.dirname(project_root), 'services', 'matrix-gateway', '.env')

    if not os.path.exists(env_path):
        print(f"❌ Fehler: .env-Datei nicht gefunden unter {env_path}")
        sys.exit(1)
        
    load_dotenv(env_path)
    
    db_url = os.getenv("DATABASE_URL")
    gpkg_path = os.getenv("BKG_GPKG_PATH")
    
    if not db_url or not gpkg_path:
        print("❌ Fehler: DATABASE_URL oder BKG_GPKG_PATH fehlt in der .env")
        sys.exit(1)

    # SQLAlchemy Engine für den GeoPandas-Bulk-Stream vorbereiten
    # Passt die URI von 'postgres://' auf 'postgresql://' an für SQLAlchemy-Kompatibilität
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(db_url)

    # 2. Datenhygiene beim Start via nativem psycopg2-Treiber
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cursor = conn.cursor()
        
        print("🧹 Bereinige bestehende Tabellenstrukturen im Kaskaden-Verfahren...")
        cursor.execute("TRUNCATE TABLE public.main_zones CASCADE;")
        cursor.execute("TRUNCATE TABLE public.bkg_lan_names CASCADE;")
        cursor.execute("TRUNCATE TABLE public.bkg_krs_names CASCADE;")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ DB-Verbindungsfehler beim Bereinigen: {e}")
        sys.exit(1)

    # 3. RAM-schonender Import der Namens-Nachschlagetabellen (Ohne Geometrien!)
    print("📦 Importiere Bundesländer (bkg_lan_names)...")
    df_lan = gpd.read_file(gpkg_path, layer="vg25_lan", ignore_geometry=True)
    # WICHTIG: Duplikate explizit basierend auf der PRIMARY KEY Spalte 'ARS' kicken!
    df_lan_filtered = df_lan[["ARS", "GEN"]].drop_duplicates(subset=["ARS"], keep="first")
    df_lan_filtered.to_sql("bkg_lan_names", engine, if_exists="append", index=False)

    print("📦 Importiere Landkreise (bkg_krs_names)...")
    df_krs = gpd.read_file(gpkg_path, layer="vg25_krs", ignore_geometry=True)
    # Analog für die Landkreise, falls dort Bodensee-Anteile doppeln
    df_krs_filtered = df_krs[["ARS", "GEN"]].drop_duplicates(subset=["ARS"], keep="first")
    df_krs_filtered.to_sql("bkg_krs_names", engine, if_exists="append", index=False)

    # 4. Laden und Verarbeiten der Gemeinde-Hauptzonen (admin_level = 8)
    print("🗺️ Lade Gemeindegrenzen aus GeoPackage (Das kann einen Moment dauern)...")
    gdf_gem = gpd.read_file(gpkg_path, layer="vg25_gem")

    # Projektion auf das globale GPS-Standardformat (WGS84 / EPSG:4326) erzwingen
    if gdf_gem.crs != "EPSG:4326":
        print("🔄 Projiziere Geometrien auf EPSG:4326 (WGS84)...")
        gdf_gem = gdf_gem.to_crs("EPSG:4326")

    # Flexibler Spalten-Finder für die Einwohnerzahl (BKG-Varianten abfangen)
    ewz_col = None
    for candidate in ["EWZ", "E_EWZ", "EINWOHNER"]:
        if candidate in gdf_gem.columns:
            ewz_col = candidate
            print(f"🔍 Einwohnerzahl-Spalte im BKG-Satz gefunden: '{ewz_col}'")
            break

    # Filterung: Fokus auf kleinere und mittlere Kommunen
    if ewz_col:
        print("⏳ Filterung der Großstädte (> 100.000 Einwohner) für das ländliche Mesh...")
        gdf_gem[ewz_col] = pd.to_numeric(gdf_gem[ewz_col], errors="coerce").fillna(0)
        gdf_gem_filtered = gdf_gem[gdf_gem[ewz_col] < 100000].copy()
    else:
        print("⚠️ Warnung: Keine bekannte Einwohner-Spalte gefunden. Großstadt-Filter wird übersprungen!")
        gdf_gem_filtered = gdf_gem.copy()

    # 5. Daten-Synthese und Mapping auf das neue Hybrid-Schema
    print("🛠️ Bereite DataFrame für die Tabelle 'main_zones' vor...")
    
    # Temporäre Mapping-Dictionaries für die Klartext-Namen erzeugen
    lan_map = dict(zip(df_lan_filtered["ARS"], df_lan_filtered["GEN"]))
    krs_map = dict(zip(df_krs_filtered["ARS"], df_krs_filtered["GEN"]))

    # Extrahiere die ARS-Präfixe zur Verknüpfung der Namen
    gdf_gem_filtered["lan_ars"] = gdf_gem_filtered["ARS"].str.slice(0, 2)
    gdf_gem_filtered["krs_ars"] = gdf_gem_filtered["ARS"].str.slice(0, 5)

    # Erzeuge das finale Daten-Layout für die Datenbank
    df_final = pd.DataFrame()
    df_final["ars_code"] = gdf_gem_filtered["ARS"]
    df_final["zone_name"] = gdf_gem_filtered["GEN"]
    df_final["admin_level"] = 8  # Fixiert auf BKG Gemeindeebene
    df_final["bundesland"] = gdf_gem_filtered["lan_ars"].map(lan_map).fillna("Unbekannt")
    df_final["landkreis"] = gdf_gem_filtered["krs_ars"].map(krs_map).fillna("Unbekannt")
    df_final["is_polaris_space"] = False  # Standardmäßig inaktiv bis zur Aktivierung im Rathaus
    
    # Geometrie wieder anfügen
    gdf_final = gpd.GeoDataFrame(df_final, geometry=gdf_gem_filtered["geometry"])

    # 6. Bulk-Stream in die PostgreSQL / PostGIS Datenbank zünden
    print(f"🔥 Schiebe {len(gdf_final)} Gemeinden in die Tabelle 'main_zones'...")
    gdf_final.to_postgis("main_zones", engine, if_exists="append", index=False)

    print("✅ BKG Base Importer erfolgreich beendet! Das Datenfundament steht.")

if __name__ == "__main__":
    main()
