# POLARIS-Gateway

POLARIS ist ein offenes, dezentrales Kommunikations-Framework auf Basis des Matrix-Protokolls. Das System bindet Nutzer vollautomatisch und datenschutzkonform basierend auf ihrem aktuellen geografischen Standort in relevante lokale Matrix-Räume (z. B. Gemeinde- oder Ortsteil-Kanäle) ein.

* **Projekt-ID:** matrix-polaris
* **Lizenz:** MIT-Lizenz (Open Source)
* **Status:** ARCHITECTURAL SPECIFICATION & DATA PROTOTYPE
* **Entwicklungsphase:** Phase 1 (Architektur-Entwurf & Geofencing-Validierung erfolgreich abgeschlossen. Das Datenmodell läuft; eine aktive Netzwerk-Kopplung an Matrix-Homeserver befindet sich in der Konzeptionsphase.)

---

## 1. Das Konzept & Die Vision

POLARIS wurde für Szenarien der digitalen Daseinsvorsorge, für kommunale Bürger-Informationssysteme und den Einsatz in lokalen Krisen- oder Inselmodi (z. B. bei großflächigen Netzausfällen mit lokal verbleibender Infrastruktur) entwickelt.

Das System löst das Problem des ortsabhängigen Informationsflusses: Statt dass Bürger mühsam nach lokalen Chat-Räumen suchen müssen, erkennt das System die Geokoordinaten und verwaltet die Raummitgliedschaften serverseitig und geräuschlos im Hintergrund (Masquerading via Matrix Application Service API). Auf den Endgeräten können somit unveränderte Standard-Matrix-Clients (wie Element oder FluffyChat) genutzt werden.

---

## 2. Verzeichnisstruktur (Polyglot-Repository)

Das Repository ist als Polyglot-Repository aufgebaut, um die schnelle Entwicklung von Ideen strikt vom hochperformanten Rechenzentrums-Betrieb zu trennen:

* `/database` – **Der funktionsfähige Kern-Prototyp:** Enthält das vollständige relationale PostGIS-Datenbankschema, die Python-Pipelines für den automatisierten Datenimport aus amtlichen Quellen (BKG-GeoPackage) und OpenStreetMap (Overpass-API) sowie die interaktive Test-CLI zur Geofencing-Simulation.
* `/prototype/` (Python) – **In Konzeption:** Optimiert für schnelle Experimente, Bot-Logik und lokale Schnittstellentests mit der Matrix-API.
* `/production/` (Rust) – **Zielarchitektur:** Die zukünftige, speichersichere und hochperformante Produktionsversion für den echten Dauereinsatz in der kommunalen DMZ (parallele Verarbeitung via DashMap).
* `/docs/` – **Zentrale technische Dokumentation:** Enthält die detaillierten Protokoll-Abläufe, Manifeste und Algorithmen-Spezifikationen.

---

## 3. Technischer Kern: Das Geofencing-Modell

Der bereits funktionstüchtige Daten-Prototyp setzt auf ein regionales 4-Tabellen-Hybridmodell in PostgreSQL/PostGIS. Um Abfragen im Bruchteil einer Millisekunde zu ermöglichen und Server-Ressourcen zu schonen, nutzt POLARIS zwei Kernparadigmen:

1. **Zweistufige geografische Kaskade:** Bei einer Standort-Aktualisierung wird die Koordinate zuerst gegen die amtlichen Gemeindegrenzen (BKG) geprüft. Erst bei einem Treffer erfolgt der detaillierte Drilldown in die untergeordneten Ortsteile (OSM). PostGIS muss so niemals tausende bundesweite Polygone gleichzeitig berechnen.
2. **In-Memory-Performance:** Der gesamte bereinigte Geodatensatz auf Gemeinde- und Ortsteilebene ist so schlank (ca. 250–300 MB), dass er vollständig im Arbeitsspeicher-Cache (`shared_buffers`) der Datenbank gehalten wird. Unterstützt durch räumliche GiST-Indizes liegen die Antwortzeiten stabil unter 0,2 Millisekunden.

---

## 4. Entwicklungs-Roadmap

Da sich das Projekt in einer frühen, evolutionären Phase befindet, sind die nächsten Meilensteine klar definiert:

* [x] **Phase 1: Daten-Prototyping** (PostGIS-Schema, BKG/OSM-Importer, Kaskaden-Logik und CLI-Tester funktionsfähig).
* [ ] **Phase 2: Die Matrix-Brücke & Gateway-Logik**
  * Aufbau der eigentlichen Gateway-Komponente als Matrix Application Service (AS) zur Anbindung an einen Synapse-Testserver.
  * Implementierung des geschwindigkeits-adaptiven Transit-Filters (Unterdrückung hyperlokaler Räume bei hoher Reisegeschwindigkeit).
  * Implementierung des 10-minütigen Hysterese-Cooldowns über die Zustandstabelle `exit_pending_users`.
  * Übersetzung der PostGIS-Ergebnisse in echte serverseitige `join`- und `leave`-Befehle via Masquerading.

---

## 5. Inbetriebnahme & Entwicklungsstand (Lokales Prototyping)

Derzeit ist das Geofencing-Datenmodell (`/database`) voll funktionsfähig implementiert. Die verschiedenen softwareseitigen Entwicklungsebenen gliedern sich wie folgt:

### 🐍 1. Prototyping-Ebene (Python)

Wird in der nächsten Ausbaustufe genutzt, um die PostGIS-Engine über Bibliotheken wie `matrix-nio` an einen Test-Homeserver anzubinden.

* Eine ausführliche Anleitung zur Einrichtung der PostGIS-Datenbank, dem Bezug der amtlichen BKG-Daten und dem Troubleshooting unter Windows (WSL1) findest du im dedizierten Sub-Readme: [**database/README.md**](./database/README.md).

### 🦀 2. Produktiver Betrieb (Rust)

Das geplante Zielbild für den echten Einsatz im kommunalen Rechenzentrum. Läuft zukünftig dank Multi-Stage-Docker-Build als minimales, hochsicheres Linux-Image und bietet maximale Thread-Sicherheit bei Massen-Zugriffen.

---

## 6. Datenschutz & Security (Privacy by Design)

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