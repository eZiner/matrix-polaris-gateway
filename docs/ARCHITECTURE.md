# 🏛️ POLARIS: System Architecture Specification

Dieses Dokument spezifiziert die logische und physikalische Architektur des POLARIS-Netzwerks. POLARIS bricht die technologische Abhängigkeit von proprietären Messenger-Infrastrukturen auf und ersetzt den klassischen App-Wildwuchs durch eine souveräne, föderierte und datenschutzfreundliche Kommunikations-Infrastruktur für Kommunen und Bürger.

---

## 🗺️ Das 3-Schichten-Modell (Physikalische Topologie)

Die Systemlandschaft ist in drei strikt voneinander isolierte Netzwerkschichten unterteilt, um maximale IT-Sicherheit für Behördennetze zu garantieren.

```text
+---------------------------------------+

|        DIE RATHAUS-VERWALTUNG         |
|   (Internes sicheres Behördennetz)    |
|  +---------------+ +---------------+  |
|  |   Fachämter   | |  Leitstelle   |  |
|  +-------+-------+ +-------+-------+  |
+----------|-----------------|----------+

           |                 |           
           v                 v           
+---------------------------------------+

|    DIE DEMILITARISIERTE ZONE (DMZ)    |
|   (Uni-Rechenzentrum / Postkasten)    |
| +-----------------------------------+ |
| |       KOMMUNALER HOMESERVER       | |
| |  +------------+   +------------+  | |
| |  | Bürgerraum |   |  Bot-Raum  |  | |
| |  | (Amt 1:1)  |   | (Geofence) |  | |
| |  +-----^------+   +-----^------+  | |
| |        |                |         | |
| |        |                v         | |
| |        |         polaris-gateway  | |
| |        |         (OSM-RAM-Check)  | |
| |  +-----+----------------+-------+ | |
| |  | Kommunale Spaces             | | |
| |  | (Schule, Warnungen, etc.)    | | |
| |  +-------------^----------------+ | |
| +----------------|------------------+ |
|                  |                    | [Globale Matrix-]
|                  +------------------->| [Föderation     ]
+------------------|--------------------+ [  (Port 8448)  ]

                   |                           |
   Bidirektionaler | Sendet                    | Chat mit
   Chat-Datenfluss | m.location                | der Welt
                   v ^                         v
+-------------------------------------------------------+

|        DIE BÜRGER-EBENE (Messenger / Element)         |
| - Bürgerraum (Zentraler Amts-Chat via Vermittlung)    |
| - Bot-Raum (Automatischer Standort-Abgleich im RAM)   |
| - Kommunale Spaces & Freie Welt (Weltweiter Chat)     |
+-------------------------------------------------------+
```

### 1. Die Rathaus-Verwaltung (Sichere Core-Zone)
* **Charakter:** Das hochgesicherte interne Behördennetz (Verwaltungsnetz/Nesta).
* **Sicherheits-Vorgabe:** Das Rathaus fungiert als unantastbare Festung. Es existieren **keine eingehenden Netzwerkverbindungen** aus dem Internet in diese Zone. 
* **Funktion:** Sachbearbeiter greifen ausschließlich kontrolliert über verschlüsselte Outbound-Proxies von innen nach außen auf den in der DMZ vorgelagerten Server zu, um Bürgeranliegen zu bearbeiten. Leitstellen speisen temporäre Gefahren-Polygone (GeoJSON) ebenfalls rein ausgehend in das Gateway ein.

### 2. Die Demilitarisierte Zone (DMZ / Universitäres Hosting)
* **Charakter:** Offen im Internet erreichbare Server-Infrastruktur, die physisch in den **Rechenzentren der regionalen Universitäten** betrieben wird.
* **Funktion:** Der kommunale Matrix-Homeserver (z. B. `matrix.goslar.de`) agiert als digitaler Postkasten im öffentlichen Raum. Die logische Administration (Rechte, Konten) verbleibt bei der jeweiligen Kommunalverwaltung, während die Uni die Hardware- und Bandbreiten-Infrastruktur stellt.
* **Netztrennung:** Selbst bei einer vollständigen Kompromittierung des Matrix-Servers ist das interne Rathaus-Netz physisch nicht erreichbar.

### 3. Die Bürger-Ebene (Client Layer)
* **Charakter:** Das öffentliche mobile Internet.
* **Schnittstelle:** Der Bürger nutzt einen standardisierten Open-Source Matrix-Messenger (wie Element oder FITKO-Neo) ohne herstellerspezifische Anpassungen (kein App-Fork).

---

## 🔑 Das Eine-Konto-Prinzip & Postersatz-Modell

Um die Akzeptanz in der Bevölkerung zu maximieren, benötigt der Bürger **genau eine Identität** für den gesamten digitalen Alltag (`@max:goslar.de`).

* **Der Vertrauensanker:** Die Identität wird über das *Postersatz-Modell* einmalig physisch und rechtssicher im lokalen Bürgerbüro (z. B. bei der Ausweisabholung) verifiziert. Der Bürger erhält einen verschlüsselten Aktivierungs-QR-Code.
* **Zwei Welten in einer App:** 
  1. **Die freie Welt:** Der Bürger nutzt das staatlich geschenkte Konto als sicheren Alltags-Messenger, um verschlüsselt mit privaten Kontakten weltweit zu kommunizieren (WhatsApp-Ersatz via offener Föderation).
  2. **Die amtliche Welt:** In derselben App greift er ohne Medienbruch auf den **Bürgerraum** und die **Infospaces** zu.

---

## 🔄 Logische Raum-Struktur in der DMZ

Der Uni-Homeserver teilt die Kommunikation logisch in drei strikt getrennte Raumbereiche auf:

### A. Der Bürgerraum (Amtliche Vermittlungsstelle)
* **Struktur:** Ein permanenter, Ende-zu-Ende verschlüsselter (Megolm) 1:1-Raum zwischen dem Bürger und dem Rathaus-Backend.
* **Logik:** Der Bürger kommuniziert mit der gesamten Verwaltung über dieses eine Fenster. Eine automatisierte Routing-Engine im Rathaus-Backend vermittelt die eingehenden Text-Threads intern asynchron an die zuständigen Fachämter (z. B. Kfz-Stelle, Standesamt), ohne dass der Bürger den Raum wechseln muss.

### B. Der Bot-Raum (Exklusiver Geo-Fencing-Kanal)
* **Struktur:** Ein separater, vordefinierter privater 1:1-Raum, in dem im Hintergrund ausschließlich der Geo-Fencing-Bot (`matrix-polaris-gateway`) läuft.
* **Logik:** Das Smartphone des Bürgers sendet periodisch standardisierte Standort-Events (`m.location`) ausschließlich in diesen Raum. Im Bürgerraum oder in anderen Chats haben GPS-Daten absolut nichts verloren.

### C. Die Kommunalen Spaces (Dynamische Infospaces)
* **Struktur:** Übergeordnete Matrix-Spaces (Container-Räume), die thematische Unterkanäle bündeln (z. B. Sektor Schule, ÖPNV-Taktung, Katastrophen-Warnungen).
* **Logik:** Der Beitritt erfolgt geräuschlos im Hintergrund über das *Auto-Join*-Verfahren, sobald der Bot-Raum einen Ortsmatch meldet.

---

## 🔒 Privacy by Design & Protokoll-Schutzmauer

### 1. Flüchtiger RAM-Abgleich
Trifft ein Standort-Event im Bot-Raum ein, wird die Koordinate flüchtig im **In-Memory-Arbeitsspeicher (RAM)** des Gateways dechiffriert und mittels einer PostGIS-Abfrage (`ST_Contains`) gegen die automatisiert aus OpenStreetMap geladenen Sektoren-Polygone geprüft. **Direkt nach dem Datenbankmatch werden die exakten GPS-Daten restlos aus dem RAM gelöscht.** Es werden zu keinem Zeitpunkt Bewegungsprofile oder historische Ortungsdaten auf der Festplatte des Servers gespeichert.

### 2. Hysterese-Schutz (Datenhygiene)
Verlässt der Bürger das Polygon einer Zelle, wird er nicht sofort gelöscht, um GPS-Springen an Sektorengrenzen abzufedern (Ping-Pong-Effekt). Das System setzt die ID auf eine temporäre `EXIT_PENDING_USERS`-Warteliste. Erst nach Ablauf einer 10-minütigen Karenzzeit triggert der Server einen automatischen `room_kick`. Der gesamte Infospace-Ordner verschwindet rückstandslos vom Smartphone des Bürgers – die Chat-Liste bleibt dauerhaft sauber.

### 3. Föderierter Ingress-Schutz (Troll-Sperre)
Um lokale Krisen- und Infokanäle vor Spam, Trolling oder Denial-of-Service-Angriffen von externen Servern (z. B. `@troll:matrix.org`) zu schützen, sind alle Infospaces auf Protokollebene über native Matrix **`restricted` Join Rules** geschützt. 
* Sämtliche teilnehmenden Kommunal- und Universitäts-Server sind in einem gemeinsamen, föderierten **Mutter-Space** (`#polaris-verbund`) organisiert.
* Ein Homeserver autorisiert den geräuschlosen *Auto-Join* eines Nutzers nur dann, wenn dessen Heimatserver kryptografisch als Mitglied dieses Mutter-Spaces verifiziert ist. Nicht-autorisierte Server werden an der Föderationsgrenze (Port 8448) hart abgewiesen.
