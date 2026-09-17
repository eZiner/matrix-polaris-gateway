**POLARIS – Technische Spezifikation der Kommunikations-Protokolle**

**Serverseitiges Geofencing und Matrix Application Service (AS) Integration**

**Version:** 2.0.0  
**Status:** ARCHITECTURE CERTIFIED (Widerspruchsfrei & Bereit zur Implementierung)  
**Schnittstellen-Basis:** Matrix Client-Server API v3 & Application Service API (MSC)  
**Zeitstempel:** Freitag, 11. September 2026

---

**🔌 1. Die Matrix Application Service (AS) Architektur**

Um einen lautlosen, automatischen Beitritt von Bürger-Smartphones in geofenced Community-, Alltags- und Krisenräume zu ermöglichen, ohne dass der Standard-Client (z. B. Element) modifiziert werden muss, agiert das POLARIS-Gateway als privilegierter **Application Service (AS)** direkt auf dem lokalen Matrix-Homeserver (Synapse) \[1.21, 1.27\].

**Die AS-Privilegien:**

- **Masquerading (Identitäts-Stellvertretung):** Das Gateway ist autorisiert, im Namen jedes lokal registrierten Matrix-Benutzers (z. B. `@user:rathaus-goslar.de`) Aktionen auszuführen – insbesondere Räumen geräuschlos beizutreten (`join`) oder diese zu verlassen (`leave`) \[1.21, 1.27\].
- **Kryptografische Absicherung:** Die Authentifizierung erfolgt über ein dediziertes, in der Synapse-Konfigurationsdatei (`polaris-as.yaml`) hinterlegtes `as_token` und ein `hs_token` für die Gegenrichtung \[1.21\].
- **Namensraum-Hoheit:** Das Gateway kontrolliert exakt definierte Räume und Aliases (z. B. mit Aliases wie `#polaris_*:domain`) \[1.21, 1.27\].

---

**🔄 2. Der serverseitige Auto-Join/Leave-Workflow**

Sobald sich ein Bürger bewegt, gleicht das System die Position im Hintergrund ab und steuert die Raumzugehörigkeit direkt auf dem Server \[1.21\]. Das Smartphone hält lediglich seine Standard-Verbindung (`/sync`) zum Homeserver \[1.27\].

**Ablaufdiagramm des Datenaustauschs:**

**text**

```
 SmartPhone (Element)             POLARIS Gateway (SLG-Core)          Synapse (Rathaus)
        │                                     │                               │
        │─── PING: GPS-Daten + User-ID ──────►│                               │
        │    (Verschlüsselt via TLS 1.3)      │                               │
        │                                     │─── SQL: ST_Contains ──┐       │
        │                                     │    (PostGIS Match)    │       │
        │                                     │◄──────────────────────┘       │
        │                                     │                               │
        │                                     │─── AS-API: /join (Masquerade)►│
        │                                     │    "Tritt !raum_id im Namen   │
        │                                     │     von @user bei"            │
        │                                     │                               │
        │                                     │◄── HTTP 200 OK ───────────────│
        │                                     │                               │
        │◄── /sync (Standard Matrix Sync) ────┼───────────────────────────────│
        │    "Raum taucht sofort in Liste auf"│                               │
```

Verwende Code mit Vorsicht.

**Die fünf Phasen im Detail:**

1. **Der Standort-Ping (Client ➡️ Gateway):** Die POLARIS-Hintergrund-App (oder ein schlankes OS-Plugin) sendet in vordefinierten Intervallen die GPS-Koordinaten verpackt in ein standardisiertes Standort-Event (`m.location` oder `m.beacon`) zusammen mit dem verifizierten Matrix-Benutzerkonto des Bürgers an das lokale Edge-Gateway.
2. **Das Geometrie-Matching (Gateway-Inhalt):** Das Rust-Gateway dechiffriert die Koordinaten **flüchtig im Arbeitsspeicher (RAM)** und jagt sie durch die PostGIS-Abfrage (`02_DATABASE_SCHEMA_SPEC.md`). Nach der Auswertung greift die **sofortige Datenhygiene**: Die GPS-Daten werden restlos aus dem RAM gelöscht; es verbleibt kein Bewegungsprofil.
3. **Föderierter Brücken-Workflow (Server-zu-Server):** Befindet sich der Bürger auf Reisen (z. B. im Urlaub an der Nordsee), meldet die DB einen Match für eine fremde Region. Der Heimat-Server sendet eine automatisierte Föderations-Anfrage (Port 8448) an den fremden Server. Auf dem Ziel-Server greift die native Matrix **restricted Join Rule**: Sie prüft kryptografisch, ob der anfragende Heimat-Server Teil des gemeinsamen globalen `#polaris-verbund` Mutter-Spaces ist. Fremde, kommerzielle Instanzen werden hart mit einem *403 Forbidden* abgewiesen.
4. **Die serverseitige Orchestrierung (Gateway ➡️ Synapse):** Bei erfolgreicher Autorisierung erfolgt der Beitritt vollautomatisch und ohne sichtbare Raumeinladung (Invite) via Masquerading-Befehl \[1.21, 1.27\].
5. **Die Client-Aktualisierung (Synapse ➡️ Element):** Der Element-Client des Bürgers empfängt die Raum-Änderung beim nächsten automatischen Long-Polling-Sync-Intervall (`GET /_matrix/client/v3/sync`) \[1.27\]. Der Raum (oder ein ganzer einklappbarer Regions-Ordner via Matrix Spaces) erscheint verzögerungsfrei und geräuschlos auf dem Display.

---

**🛰️ 3. API-Schnittstellen (REST-Payloads)**

Das Gateway nutzt für die serverseitige Steuerung folgende exakte API-Aufrufe gegen den Synapse-Server \[1.21, 1.27\]:

**A. Ad-hoc Krisenraum erstellen**

Wird von einer Blaulicht-Organisation ein neues dynamisches Schadenspolygon gezeichnet, erstellt das Gateway den Raum wie folgt \[1.21\]:

- **Endpunkt:** `POST /_matrix/client/v3/createRoom` \[1.27\]
- **Header:** `Authorization: Bearer <POLARIS_AS_TOKEN>` \[1.21\]
- **Payload:**

**json**

```
{
  "name": "EILMELDUNG - Hochwasser Innerste",
  "room_alias_name": "polaris_krisis_goslar_innerste",
  "visibility": "public",
  "preset": "public_chat",
  "initial_state": [
    {
      "type": "m.room.power_levels",
      "state_key": "",
      "content": {
        "users": {
          "@leitstelle:landkreis-goslar.de": 100,
          "@polaris_gateway:rathaus-goslar.de": 100
        },
        "users_default": 0,
        "events": {
          "m.room.message": 50,
          "m.room.avatar": 100
        },
        "events_default": 0
      }
    }
  ]
}
```

Verwende Code mit Vorsicht.

- **Architektonischer Effekt:** Durch das explizite Setzen von `"m.room.message": 50` im `power_levels`-Event wird der Raum sofort als reiner Warnkanal (Muted) initialisiert \[1.21\]. Normale Bürger (Level 0) können nur lesen; nur verifizierte Behörden-Accounts (Level 50+) dürfen Nachrichten senden \[1.21\].

**B. Privilegierter Auto-Join (Grenzübertritt)**

Sobald das Gateway einen Bürger in eine neue Zone einstuft, erfolgt der serverseitige Beitritt \[1.21, 1.27\]:

- **Endpunkt:** `POST /_matrix/client/v3/rooms/{roomId}/join` \[1.27\]
- **Query-Parameter:** `?user_id=@max.mustermann:rathaus-goslar.de` (Masquerading-Befehl via AS) \[1.21, 1.27\]
- **Header:** `Authorization: Bearer <POLARIS_AS_TOKEN>` \[1.21\]
- **Payload:** `{}` (Leerer Body, da die Steuerung rein serverseitig erfolgt).

---

**🔒 4. Das Homeserver-Whitelisting (Schutz vor Kaperung)**

Da das POLARIS-Gateway im Rathaus administrative Rechte über die lokale Synapse-Instanz besitzt, ist die Konfigurationsdatei des Gateways durch ein striktes Domain- und ARS-Whitelisting gehärtet:

1. **Zuständigkeits-Kopplung:** Das Gateway prüft bei jedem API-Befehl intern ab, ob der `ars_code` der zu schaltenden Zone exakt mit der Domain des lokalen Homeservers übereinstimmt (z. B. ARS `03153005` darf ausschließlich Aktionen auf `matrix.clausthal-zellerfeld.de` auslösen).
2. **Fremdraum-Sperre:** Es ist dem Gateway auf Code-Ebene unmöglich, im Namen lokaler User Räumen beizutreten, die auf nicht-behördlichen, externen Homeservern außerhalb des verifizierten POLARIS-Verbunds liegen. Dies verhindert, dass ein kompromittiertes Gateway als Spam- oder Überwachungs-Bot missbraucht werden kann.

---

**📡 5. Der physische IP-Ersatzweg im Katastrophen-Inselmodus**

Ein fundamentaler Design-Vorteil von POLARIS ist die vollständige Kompatibilität mit unmodifizierten Standard-Matrix-Clients \[1.21, 1.27\]. Da Element als reiner HTTP/REST- und TCP/IP-basierter Client konzipiert ist, benötigt er zwingend eine aktive IP-Netzwerkverbindung zum lokalen Homeserver \[1.21, 1.27\]. Bricht das weltweite Internet zusammen, greift die physische Ersatz-Infrastruktur vor Ort:

**A. Das kommunale Nahbereich-Not-WLAN**

Die autark per Dieselgenerator und USV weiterlaufenden Knotenpunkte (Rathäuser, Feuerwehren) aktivieren leistungsstarke Outdoor-WLAN-Access-Points.

- **Netzkennung (SSID):** Es wird ein unverschlüsseltes, offenes WLAN mit standardisierter Kennung ausgestrahlt (z. B. `NOTFUNK_POLARIS_<GEMEINDENAME>`).
- **Routing-Restriktion:** Dieses WLAN besitzt keine Verbindung zum WWW. Der lokale DHCP-Server verteilt IP-Adressen, die über statische Routen ausschließlich das lokale Edge-Gateway und das SLG-Rack im Keller ansteuern.
- **Client-Verhalten:** Das Smartphone des Bürgers bucht sich ein. Für Element stellt sich die Verbindung als normales WLAN dar. HTTP-POST-Pakete fließen über die lokale Frequenz direkt in den Synapse-Server vor Ort, wo Nachrichten sofort für alle anderen im Not-WLAN befindlichen Bürger sichtbar werden \[1.21, 1.27\].

**B. Taktische Edge-LTE/5G-Zellen (Cell-on-Wheels)**

Um größere Flächen oder abgeschnittene Ortsteile ohne WLAN-Reichweite abzudecken, führen Hilfsorganisationen (THW, Feuerwehr) mobile Anhänger mit ausfahrbaren Masten mit sich, die ein autarkes, privates Mobilfunknetz (Campusnetzwerk) aufbauen.

- **Die IP-Brücke:** Am Fuß dieser mobilen Masten befindet sich eine Richtfunk-Antenne oder ein lokaler Feldkabel-Anschluss, der direkt im regionalen Ringnetz mündet.
- **Datenfluss:** Das Smartphone bucht sich über eine behördlich freigegebene Notfall-Roaming-Funktion in die private Funkzelle ein. Element sendet seine Pakete an die IP-Adresse des lokalen Rathauses. Die Daten wandern über die Luftschnittstelle des Mastes, per Richtfunk von Kirchturm zu Kirchturm und schlagen ohne Umweg über das weltweite Internet direkt im Rathaus-Synapse-Server ein \[1.21, 1.27\].