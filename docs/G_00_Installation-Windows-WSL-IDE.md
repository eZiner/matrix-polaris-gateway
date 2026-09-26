📑 POLARIS Multi-Service Entwickler- & Betriebsleitfaden

Zielgruppe: Core-Entwickler & DevOps  
Plattform: Windows 11 mit WSL-1/2 (Ubuntu) & VS-Code (Remote-WSL)  
Architektur: Polyglott (Rust Matrix-Gateway + Python PostGIS-Pipelines)

---

1. Das hybride Ökosystem (Architektur-Verständnis)

Das POLARIS-Projekt ist als Service-Orientierte Architektur (SOA) im Repository unter /services/ strukturiert. Da wir auf einem Windows-Laufwerk (z. B. /mnt/g/) mittels des Linux-Subsystems (WSL) entwickeln, müssen wir die Zuständigkeiten der Betriebssysteme strikt trennen:

- Der Python-Layer (/database): Läuft nativ im Linux-Subsystem. Alle Bibliotheken zur Geodatenverarbeitung (geopandas, shapely, psycopg2) sind als nativer ELF-Linux-Code in einem isolierten Linux-.venv installiert.
- Der Rust-Layer (/services/matrix-gateway): Läuft ebenfalls im Linux-Subsystem für die Code-Analyse und das lokale Debugging, wird im produktiven Betrieb jedoch über Docker-Compose in ein Linux-Image verpackt.
- Die IDE (VS-Code): Läuft im WSL-Remote-Modus. Das Windows-Frontend dient nur als Anzeige; der eigentliche VS-Code-Server läuft innerhalb von Ubuntu.

---

2. Ersteinrichtung & WSL-Vorbereitung

Wenn das Repository frisch geklont wird oder ein neuer Entwickler einsteigt, müssen im Ubuntu-Terminal (root@.) einmalig die kryptografischen und System-Werkzeuge installiert werden, da das WSL-Basis-Image extrem minimalistisch ist:

bash

```
# 1. System-Pakete aktualisieren und Compiler-Werkzeuge für OpenSSL nachinstallieren
apt-get update && apt-get install -y python3-venv python3-pip pkg-config libssl-dev curl

# 2. Die offizielle Rust-Toolchain nativ im Linux-Subsystem installieren
curl --proto '=https' --tlsv1.2 -sSf https://rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

---

3. Die Python-Geodaten-Pipeline (/database)

Das NTFS-I/O-Problem (Fallstrick os error 5)

Beim Entpacken komplexer Python-Pakete wie numpy oder geopandas auf ein gemountetes Windows-Laufwerk verliert die WSL-Dateisystembrücke (drvfs) bei schnellen Schreibzugriffen die Verbindung. Windows blockiert den Pfad, was zu OS-Errno 5 führt.

Die Lösung: Installation im RAM via uv

Wir nutzen uv (das ultraschnelle Rust-Paket-Tool) und zwingen das System, temporäre Daten im Linux-RAM (/tmp) abzuwickeln:

bash

```
cd /mnt/g/projects/polaris/matrix-polaris-gateway/database

# 1. Lokales Linux-Environment anlegen und aktivieren
python3 -m venv .venv
source .venv/bin/activate

# 2. 'uv' und neutrale Zeitzone erzwingen (umgeht Windows-Laufwerksscans der tzdata)
export TZ=UTC
pip install uv

# 3. Installation ohne Cache direkt in die Linux-Struktur
uv pip install --no-cache -r requirements.txt
```



---

4. IDE-Konfiguration (VS-Code im Remote-Modus)

Damit VS-Code Python- und Rust-Tasks nicht vermischt und fehlerfrei debuggt, muss das Projekt im WSL-Modus geöffnet sein (Blaues Quadrat unten links: WSL:Legacy - für WSL-1).

Wichtig: Benötigte Erweiterungen innerhalb von WSL installieren

Im Erweiterungs-Menü (Strg + Shift + X) müssen folgende Plugins explizit für den WSL-Server installiert sein:

1. Python (Microsoft)
2. Python Debugger (v2026.x+, Microsoft – stellt den debugpy-Kern bereit)
3. rust-analyzer (Für die Rust-Typisierung)
4. SQLTools & SQLTools PostgreSQL Driver (Empfohlen)

Die globalen Workspace-Konfigurationen (.vscode/)

.vscode/settings.json

Zwingt VS-Code, für Python-Skripte das Linux-vEnv zu nutzen und injiziert Umgebungsvariablen aus der .env direkt in die Shell:

json

```
{
    "python.defaultInterpreterPath": "${workspaceFolder}/database/.venv/bin/python",
    "python.analysis.extraPaths": [
        "${workspaceFolder}/database/.venv/lib/python3.10/site-packages"
    ],
    "python.terminal.activateEnvInCurrentTerminal": true,
    "python.terminal.executeInFileDir": true,
    "python.terminal.useEnvFile": true
}
```

Verwende Code mit Vorsicht.

.vscode/launch.json

Ermöglicht das Starten beider Sprachen per F5 über das „Ausführen & Debuggen“-Menü (Käfer-Symbol) \[1.1\]. Die Arbeitsverzeichnisse (cwd) sind strikt getrennt \[1.1\].

json

```
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "🐍 POLARIS: Python Skript starten",
            "type": "debugpy",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}/database",
            "python": "${workspaceFolder}/database/.venv/bin/python"
        },
        {
            "type": "lldb",
            "request": "launch",
            "name": "Debug executable 'matrix-polaris-gateway'",
            "cargo": {
                "args": ["build", "--bin=matrix-polaris-gateway", "--package=matrix-polaris-gateway"],
                "filter": {"name": "matrix_polaris_gateway", "kind": "bin"}
            },
            "args": [],
            "cwd": "${workspaceFolder}/services/matrix-gateway"
        }
    ]
}
```

Verwende Code mit Vorsicht.

---

5. Laufender Betrieb & Kompilierung

Rust-Gateway prüfen/starten

Da wir auf einem Windows-Laufwerk kompilieren, biegen wir das Cargo-Target-Verzeichnis ebenfalls in das native Linux-Dateisystem (/tmp) um, um I/O-Fehler beim Bauen von Krypto-Bibliotheken (openssl-sys) zu verhindern:

bash

```
cd /mnt/g/projects/polaris/matrix-polaris-gateway/services/matrix-gateway

# Temporären Build-Ordner ins Linux-Dateisystem auslagern
export CARGO_TARGET_DIR=/tmp/cargo-target

# Gateway starten
cargo run --bin matrix-polaris-gateway
```

Verwende Code mit Vorsicht.

Python-CLI-Manager starten

Öffne database/cli_manager.py im Editor, wähle im Käfer-Menü 🐍 POLARIS: Python Skript starten und drücke F5.

💤 Standby-Verbindungsabbruch beheben

Wenn Windows aus dem Standby erwacht, meldet VS-Code Disconnected from WSL-Legacy.

- Die schnelle Lösung: Wenn du noch eine separate Ubuntu-Konsole offen hast, wechsle dort hinein und tippe im Projektverzeichnis einfach code . ein. Das zwingt das Windows-Frontend, sich sofort wieder an die lebende Linux-Sitzung anzukoppeln!