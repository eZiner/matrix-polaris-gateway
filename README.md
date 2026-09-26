# POLARIS-Gateway

POLARIS ist ein offenes, dezentrales Kommunikations-Framework auf Basis des Matrix-Protokolls. Das System bindet Nutzer vollautomatisch und datenschutzkonform basierend auf ihrem aktuellen geografischen Standort in relevante lokale Matrix-Räume (z. B. Gemeinde- oder Ortsteil-Kanäle) ein.

* **Projekt-ID:** matrix-polaris
* **Lizenz:** MIT-Lizenz (Open Source)
* **Status:** FUNCTIONAL MICROSERVICES ECOSYSTEM

---

## 1. Das Konzept & Die Vision

POLARIS wurde für Szenarien der digitalen Daseinsvorsorge, für kommunale Bürger-Informationssysteme und den Einsatz in lokalen Krisen- oder Inselmodi (z. B. bei großflächigen Netzausfällen mit lokal verbleibender Infrastruktur) entwickelt.

Das System löst das Problem des ortsabhängigen Informationsflusses: Statt dass Bürger mühsam nach lokalen Chat-Räumen suchen müssen, erkennt das System die Geokoordinaten und verwaltet die Raummitgliedschaften serverseitig und geräuschlos im Hintergrund (Masquerading via Matrix Application Service API). Auf den Endgeräten können somit unveränderte Standard-Matrix-Clients (wie Element oder FluffyChat) genutzt werden.

---

## 2. Verzeichnisstruktur (Polyglot-Repository)

Das POLARIS-Ökosystem ist modular aufgebaut, um eine strikte funktionale Trennung zwischen den Geodaten-Infrastrukturen und den eigentlichen Kommunikations-Diensten zu gewährleisten:

```text
matrix-polaris-gateway/
├── .github/workflows/      # 🚀 Zentrales CI/CD (unabhängige Pipelines für Services)
├── database/               # 🗺️ PostGIS-Schema, Geodaten-Pipelines & Python-Importe
│   ├── .venv/              # Isoliertes natives Linux-Environment (via uv verwaltet)
│   ├── cli_manager.py      # Interaktiver PostGIS Polygon-Drilldown
│   └── requirements.txt    # Abhängigkeiten (GeoPandas, SQLAlchemy, etc.)
├── docs/                   # 📄 API-Spezifikationen, Architektur-Blueprints & Handbücher
├── services/               # ⚙️ DIE PRODUKTIVEN DIENSTE
│   ├── matrix-gateway/     # 🦀 Core-Service: Matrix Application Service (Rust AS)
│   │   ├── src/            # Rust Quellcode (Geofencing- & Hysterese-Logik)
│   │   ├── Cargo.toml      # Rust Abhängigkeiten & Workspace-Konfiguration
│   │   └── .env            # Zentrale Gateway-Konfigurationsdatei
│   ├── admin-api/          # ⏳ Platzhalter: REST-API für die Verwaltung (Go/Node)
│   └── admin-web/          # ⏳ Platzhalter: Webportal für Krisenstäbe (TS/React)
├── Cargo.toml              # 🛠️ Globales Rust-Workspace-Manifest (Root-Ebene)
├── docker-compose.yml      # 🐳 Lokaler Orchestrator (PostGIS, Synapse & Gateway)
└── README.md               # 📖 Der zentrale Einstiegspunkt
```

---

## 3. Technischer Kern & Geofencing

Das System nutzt eine zweistufige geografische Kaskade in PostgreSQL/PostGIS, eine unverschlüsselte Zwei-Kanal-Strategie (Space-Shifting) zur Entlastung bei Großveranstaltungen und speicheroptimierte In-Memory-Performance.

---

## 4. Roadmap & Inbetriebnahme

Das System nutzt eine zweistufige geografische Kaskade in PostgreSQL/PostGIS, eine unverschlüsselte Zwei-Kanal-Strategie (Space-Shifting) zur Entlastung bei Großveranstaltungen und speicheroptimierte In-Memory-Performance.

---

## 5. Datenschutz & Security (Privacy by Design)

* **Keine Bewegungsprofile:** Der mathematische PostGIS-Abgleich (`ST_Contains`) erfolgt ausschließlich flüchtig im Arbeitsspeicher (RAM). Die exakten GPS-Daten werden sofort nach der Raum-ID-Ermittlung verworfen und nicht dauerhaft protokolliert.
* **Datenhygiene (Hysterese-Schutz):** Verlässt ein Bürger eine Zone, greift eine 10-minütige Karenzzeit (gespeichert in `exit_pending_users`). Erst danach erfolgt der automatische Austritt. Der Raum verschwindet vom Smartphone, was „Gruppenleichen“ im Messenger verhindert.
* **Troll-Schutz:** Alle Räume sind über native Matrix *Restricted Join Rules* an einen gemeinsamen übergeordneten Mutter-Space der Kommune gekoppelt. Externe, nicht-verifizierte Server werden an der Föderationsgrenze automatisch abgewiesen.

---

## 👥 Mitmachen & Community

POLARIS versteht sich als gesamtgesellschaftliches Infrastrukturprojekt für die digitale Souveränität im kommunalen Raum. Wir laden Entwickler, Netzwerk-Architekten, Kommunalpolitiker und Verwaltungs-Spezialisten herzlich ein, an den Konzepten und der Implementierung mitzuwirken.

---

## ⚠️ Status des Projekts & Haftungsausschluss

**Dieses Projekt ist ein privater, nicht-kommerzieller Prototyp (Proof of Concept).**

Bitte beachten Sie für die Nutzung und Weiterentwicklung folgende Punkte:

- **Entwicklungsstatus:** Diese Software befindet sich im Prototypen-Stadium. Sie ist NICHT für den produktiven Einsatz bereit und sollte ohne vorherige, unabhängige Sicherheitsprüfungen nicht in Live-Systemen eingesetzt werden.
- **KI-Unterstützung:** Teile dieses Codes und der Dokumentation wurden mit Unterstützung von Google-KI-Werkzeugen erstellt. Alle Inhalte wurden vom Autor manuell geprüft, überarbeitet und getestet. Eine absolute Fehlerfreiheit kann jedoch nicht garantiert werden.
- **Haftungsausschluss:** Entsprechend der MIT-Lizenz wird die Software ohne jegliche Gewährleistung ("as is") zur Verfügung gestellt. Der Autor übernimmt keine Haftung für Systemfehler, Datenverlust, Sicherheitslücken oder etwaige Lizenzkonflikte durch eingebundene Pakete (Dependencies).
- **Zukünftige Trägerschaft:** Dieses Repository dient als technische Grundlage. Es ist vorgesehen, dass die finale redaktionelle, technische und rechtliche Verantwortung sowie die Code-Audits vor einem produktiven Rollout an eine öffentliche Institution oder eine gemeinnützige Organisation (NGO) übertragen werden.