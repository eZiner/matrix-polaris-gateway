# POLARIS-Gateway - Strategisches Architektur-Manifest

* **Projekt-ID:** matrix-polaris
* **Komponente:** matrix-polaris-gateway
* **Version:** 2.2.1 (Entwurfs-Spezifikation)
* **Lizenz:** MIT-Lizenz (Open Source)
* **Status:** ARCHITECTURAL SPECIFICATION & PROTOTYPE (Konzeptioneller Entwurf, Datenmodell als Python/PostGIS-Prototyp implementiert)

---

## 1. Vision und Einsatzzweck

POLARIS (PostgreSQL Local Autonomy Room Insertion System) ist ein konzeptionelles Framework für ein dezentrales, ortsabhängiges Kommunikationsnetzwerk auf Basis des Matrix-Protokolls. Das System ist speziell für Szenarien der digitalen Daseinsvorsorge, für kommunale Bürger-Informationssysteme und den Einsatz in lokalen Krisen- oder Inselmodi (z. B. bei Netzausfällen mit lokal verbleibender Infrastruktur) konzipiert.

Das Kernziel ist es, Nutzer datenschutzkonform und vollautomatisch basierend auf ihrem aktuellen geografischen Standort in relevante lokale Matrix-Räume (z. B. Gemeinde- oder Ortsteil-Kanäle) einzubinden, ohne dass eine manuelle Raumsuche oder eine clientseitige Modifikation der Matrix-Apps erforderlich ist.

---

## 2. Systemarchitektur und Schichtenmodell

Das Gesamtsystem gliedert sich in drei logische Schichten:

1. **Matrix Client Layer (Endgeräte):**
   Das Framework setzt auf bestehende Standards. Bürger nutzen unveränderte, offizielle Matrix-Clients (z. B. Element, FluffyChat). Die Positionsdaten (GPS-Koordinaten) werden über standardisierte Mechanismen oder dedizierte, schlanke Zusatzmodule an den Homeserver übermittelt.
2. **Matrix Homeserver Layer (Infrastruktur):**
   Ein oder mehrere föderierte Matrix-Homeserver (z. B. Synapse, Dendrite) verwalten die Benutzerkonten, Räume und **kryptografischen Schlüssel**. Diese Schicht stellt die Ausfallsicherheit im Verbund sicher. Die Kommunikation mit den Endgeräten erfolgt über das Matrix /sync-Protokoll.
3. **POLARIS Gateway & Data Layer:**
   Das Gateway verbindet die Matrix-Welt über die Matrix Application Service API mit der geografischen Datenbank. Es ist funktional in zwei Bereiche unterteilt:
   * App-Service-Komponente (Konzept/Soll-Zustand): Agiert als privilegierter Matrix Application Service. Es fängt Standort-Events ab und führt die join- und leave-Befehle im Namen der Nutzer via Masquerading aus. Diese Komponente befindet sich in der Konzeptionsphase.
   * Geofencing-Engine (Implementierter Prototyp): Eine PostgreSQL-Datenbank mit PostGIS-Erweiterung. Sie hält das administrative Raummodell (Bundesländer, Landkreise, Gemeinden und Ortsteile) im Arbeitsspeicher-Cache und wertet Koordinaten in unter 0,2 Millisekunden aus.

---

## 3. Die Kern-Paradigmen

### 3.1 Geografische Kaskadierung statt globaler Indizierung

Um die Abfragezeiten gering zu halten, nutzt POLARIS eine zweistufige räumliche Kaskade:

1. Hauptzone (admin_level 8): Vorfilterung gegen die amtlichen Gemeindegrenzen des Bundesamtes für Kartographie und Geodäsie (BKG).
2. Subzone (admin_level 9/10 / OSM): Feingranulare Bestimmung des Ortsteils oder der Krisen-Sonderzone innerhalb der ermittelten Gemeinde.

### 3.2 Flüchtige In-Memory-Verarbeitung und Datenschutz

Das Gateway folgt dem Prinzip „Privacy by Design“:

* Geografische Koordinaten werden vom Gateway als flüchtige Events verarbeitet.
* Es erfolgt keine dauerhafte Speicherung von Bewegungsprofilen in der Datenbank. Die Koordinate wird lediglich für die Dauer der PostGIS-Abfrage im RAM gehalten, um die Raum-IDs zu bestimmen.
* Einzige Ausnahme im Datenmodell ist eine Hysterese-Tabelle (`exit_pending_users`), die temporär Zeitstempel für den geplanten Raumaustritt speichert, um ein "Springen" an Zonenrändern zu verhindern.

### 3.3 Schutz vor Infrastruktur-Überlastung (Transit-Filter)

Um zu verhindern, dass schnelle Bewegungen (z. B. Fahrten in Zügen oder auf Autobahnen) zu permanenten Beitritts- und Austritts-Wellen führen (State Resolution Storms), sieht die Architektur einen geschwindigkeits-adaptiven Filter vor. Ab einer definierten Geschwindigkeitsschwelle wird die Einwahl in hyperlokale Ortsteil-Räume blockiert und der Nutzer stattdessen temporär in der übergeordneten Gemeinde- oder Kreis-Zone konsolidiert.

---

## 4. Aktueller Entwicklungsstand und Roadmap

Das Projekt befindet sich in der aktiven Entwurfs- und Prototyping-Phase.

* **Verfügbar (Code-Basis):** Das vollständige relationale PostGIS-Datenbankschema sowie die Python-Skripte für den automatisierten Datenimport (BKG-GeoPackages & OpenStreetMap Overpass-API) und die Geofencing-Simulation via CLI sind voll funktionsfähig implementiert.
* **In Planung (Nächste Schritte):** Die native Implementierung der App-Service-Logik (vorzugsweise in Rust oder Python) zur Anbindung an die Matrix-Schnittstellen sowie die softwareseitige Umsetzung des geschwindigkeits-adaptiven Transit-Filters.