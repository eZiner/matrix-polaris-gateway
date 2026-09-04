#!/bin/bash
# =============================================================================
# POLARIS LOCAL GEODATA IMPORT (Python Bridge)
# =============================================================================
# Beschreibung: Führt den robusten lokalen Geodaten-Import der OSM-Daten aus.
#               Ruft das bewährte Python-Skript auf, um das OSM-JSON-Format
#               ohne Netzwerk-Abhängigkeiten in PostGIS einzulesen.
# =============================================================================

# Stoppe das Skript sofort, falls ein Fehler auftritt
set -e

# Ermittle das Verzeichnis, in dem dieses Skript liegt
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Wechsle in das Hauptverzeichnis des Projekts
cd "$PROJECT_DIR"

LOCAL_FILE="./database/goslar_schools.json"

# Prüfen, ob die heruntergeladene Datenbasis am Platz liegt
if [ ! -f "$LOCAL_FILE" ]; then
    echo "❌ Fehler: Die Datei $LOCAL_FILE wurde nicht gefunden!"
    echo "Bitte lade die Daten über Overpass Turbo (https://overpass-turbo.eu) als"
    echo "Rohdaten herunter und speichere sie als 'goslar_schools.json' im database-Ordner."
    exit 1
fi

# Der eigentliche Import-Part via lokalem Python-Parser
python3 ./database/import_osm.py
