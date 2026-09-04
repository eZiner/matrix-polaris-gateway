# ⚙️ Technical Workflow Specification: Federated Space Auto-Join

Dieses Dokument beschreibt den exakten, schrittweisen technischen Ablauf auf Protokoll- und Datenbankebene, wenn ein Endgerät einen geografischen Zellenwechsel vollzieht. Der gesamte Prozess ist geräuschlos (*no invites*) und datenschutzfreundlich (*In-Memory Processing*) konzipiert.

---

## 🛠️ Der Ablauf im Detail

### 1. Event-Trigger & Transport (Client-Ebene)
1. Die GPS-Hardware des Smartphones registriert im Hintergrund eine signifikante Standortänderung.
2. Der standardisierte Matrix-Client (z. B. Element) verpackt die Koordinaten (WGS84) in ein natives Matrix-Standort-Event (`m.location` oder `m.beacon`).
3. Das Event wird mittels Ende-zu-Ende-Verschlüsselung (Megolm) chiffriert.
4. Der Client sendet das Event via HTTPS-POST **ausschließlich in den einen, vordefinierten privaten 1:1-Raum**, in dem im Hintergrund der lokale Geo-Fencing-Bot läuft.

### 2. Flüchtige In-Memory-Verarbeitung (Heimat-Gateway)
1. Der Heimat-Bot (`matrix-polaris-gateway`) empfängt das verschlüsselte Event asynchron über die Event-Schleife.
2. Der Bot ruft den temporären Raumschlüssel ab und dechiffriert die Koordinaten **flüchtig im Arbeitsspeicher (RAM)**.
3. Das Gateway setzt eine asynchrone, räumliche SQL-Abfrage an die lokale PostGIS-Datenbank ab:
   ```sql
   SELECT matrix_space_id 
   FROM polaris_infospaces 
   WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(\$1, \$2), 4326));
   ```
4. **Sofortige Datenhygiene:** Unmittelbar nach der SQL-Rückmeldung werden die exakten GPS-Koordinaten **restlos aus dem RAM gelöscht**. Der Server vergisst die genaue Position augenblicklich, um die Erstellung von Bewegungsprofilen physisch unmöglich zu machen.
5. Die Datenbank liefert als Match die ID eines übergeordneten Containers zurück: den **Infospace** (z. B. `!cuxhaven_space:cuxhaven.de`).

### 3. Föderierter Brücken-Workflow (Server-zu-Server)
Falls der gematchte Infospace auf einem fremden, entfernten Homeserver des Verbunds liegt, greift das Matrix-Föderationsprotokoll (Port 8448):
1. Der Heimat-Server (`matrix.goslar.de`) sendet eine automatisierte Föderations-Anfrage im Namen des Nutzers an den fremden Server (`matrix.cuxhaven.de`).
2. Der fremde Server empfängt den Beitrittswunsch (`join`) für den Infospace `!cuxhaven_space:cuxhaven.de`.
3. **Die Protokoll-Schutzmauer:** Auf dem entfernten Server greift die native Matrix **`restricted` Join Rule**. Der Ziel-Server prüft kryptografisch: *„Ist der anfragende Heimat-Server Teil unseres gemeinsamen universitären **Mutter-Spaces** (`#polaris-verbund`)?“*
4. **Die Autorisierung:** Da der Server als vertrauenswürdig verifiziert ist, wird das Beitritts-Event im globalen Raumzustand (`Room State`) repliziert. Externe Server (wie `matrix.org`) werden an dieser Schnittstelle hart mit einem `403 Forbidden` abgewiesen.

### 4. Geräuschloser Auto-Join im Client (Bürger-Ebene)
1. Durch die protokollseitige Autorisierung wird der Nutzer `@max:goslar.de` **vollautomatisch und ohne aufploppende Einladung (Invite)** in den Infospace eingeklinkt.
2. **Der UI-Effekt im Messenger:** In der Element-App des Bürgers erscheint geräuschlos ein einklappbarer Ordner (der Space) für die neue Region.
3. Durch die native Matrix-Spaces-Vererbung sind alle im Container liegenden Unterkanäle (Schule, ÖPNV, Katastrophenschutz) für das Smartphone sofort lesbar. Der Bürger muss keinen einzigen Raum manuell abonnieren.

### 5. Das automatisierte Exit-Protokoll (Datenhygiene)
1. Verlässt das Endgerät das Polygon, meldet die PostGIS-Abfrage des Heimat-Bots bei der nächsten periodischen Prüfung den Zustand `OUTSIDE`.
2. Um GPS-Ungenauigkeiten an Sektorengrenzen abzufedern (Ping-Pong-Effekt), wird die User-ID für diese Zone auf die interne Warteliste `EXIT_PENDING_USERS` gesetzt.
3. Ein asynchroner Hintergrund-Thread prüft die Zeitstempel der Warteliste.
4. Nach Ablauf eines 10-Minuten-Hysterese-Cooldowns sendet der Heimat-Bot ein Signal an das entfernte Gateway.
5. Das entfernte Gateway führt einen automatisierten Server-Kick (`kick`) für den Nutzer aus dem übergeordneten Infospace aus.
6. **Das Ergebnis:** Der gesamte Ordner inklusive aller Unterkanäle verschwindet schlagartig und rückstandslos vom Smartphone des Bürgers. Die Chat-Liste bleibt sauber.
