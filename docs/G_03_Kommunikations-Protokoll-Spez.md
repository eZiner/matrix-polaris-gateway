# POLARIS-Gateway – Kommunikations-Protokoll-Spezifikation

* **Projekt-ID:** matrix-polaris
* **Komponente:** matrix-polaris-gateway (Communication Layer)
* **Version:** 1.0.0 (Soll-Spezifikation)
* **Lizenz:** MIT-Lizenz (Open Source)
* **Status:** ARCHITECTURAL SPECIFICATION (Konzeptionelles Soll-Protokoll; Schnittstellen für das zukünftige Gateway-Modul definiert, noch nicht im Code implementiert)

---

## 1. Integrationsmodell in das Matrix-Ökosystem

Das POLARIS-Gateway ist architektonisch als privilegierter **Matrix Application Service (AS)** konzipiert. Der Application Service dockt direkt über die offizielle AS-API an den Matrix-Homeserver (z. B. Synapse) an.

### Privilegiertes Masquerading

Durch die AS-Registrierung erhält das Gateway das Recht zum **Masquerading** (Identitäts-Stellvertretung). Das bedeutet:

* Das Gateway kann im Namen registrierter Benutzer vollautomatisch Aktionen ausführen.
* Die Ein- und Auswahl in geografische Räume (`join` / `leave`) erfolgt serverseitig und geräuschlos im Hintergrund.
* Auf dem Endgerät des Bürgers ist keine Modifikation der Standard-Matrix-Apps (wie Element) erforderlich. Die Raumänderungen werden beim nächsten regulären Synchronisations-Intervall (`GET /_matrix/client/v3/sync`) des Clients wirksam.

---

## 2. Authentifizierung und Sicherheits-Whitelisting

Um Missbrauch und unberechtigtes Raum-Sponsoring zu verhindern, implementiert die Architektur eine strikte Sicherheitsbarriere:

1. **Domänen-Bindung:** Das Gateway akzeptiert ausschließlich Registrierungen und Standort-Events von Benutzer-IDs, deren Homeserver-Domain exakt mit der konfigurierten Behörden- oder Kommunal-Domain des validierten Verbunds übereinstimmt (z. B. `@buerger:matrix.landkreis-goslar.de`).
2. **Amtlicher Regionalschlüssel (ARS):** Ein Raum-Beitritt wird nur dann autorisiert, wenn die Ziel-Raum-ID in der Tabelle `polaris_spaces` einem verifizierten ARS-Code zugeordnet ist. Das Gateway kann Benutzer niemals in externe oder nicht-autorisierte Räume zwingen.

---

## 3. API-Endpunkte und JSON-Payloads (Soll-Spezifikation)

Die Kommunikation zwischen dem (noch zu implementierenden) Gateway-Modul und der Geofencing-Engine bzw. dem Homeserver basiert auf folgendem REST-Protokoll:

### 3.1 Standort-Aktualisierung (Inbound-Event an das Gateway)

Wird ausgelöst, wenn ein Client neue Geokoordinaten an das System sendet.

* **Methode:** `POST`
* **Pfad:** `/_matrix/app/v1/polaris/location`
* **Payload:**

```json
{
  "user_id": "@user:matrix.localbehörde.de",
  "device_id": "ABCDEFGH",
  "timestamp": 1711971168,
  "location": {
    "latitude": 51.8105,
    "longitude": 10.3341,
    "accuracy_meters": 15.0
  },
  "motion": {
    "velocity_kmh": 4.5,
    "heading_degrees": 180.0
  }
}
```

### 3.2 Raum-Zuweisung (Outbound-Aktion an den Homeserver)

Nach der PostGIS-Abfrage generiert das Gateway die entsprechenden Matrix-Raumbefehle.

* **Methode:** `POST`
* **Pfad:** `/_matrix/client/v3/rooms/{roomId}/join` oder `/leave`
* **Header:** `Authorization: Bearer <AS_TOKEN>`
* **URL-Parameter:** `user_id=@user:matrix.localbehörde.de` (via Masquerading)

---

## 4. Raum-Berechtigungsstufen (Power Levels)

Um in Krisenlagen die Informationsintegrität zu wahren, definiert das Protokoll für automatisch erzeugte Räume standardisierte Matrix-Power-Levels:

* **Typ** `COMMUNITY` **(Lokale Bürgerkanäle):**
  * Behörden/Moderatoren (Power Level 50/100): Volle Schreib- und Moderationsrechte.
  * Bürger (Power Level 0): Standard-Schreibrechte für den lokalen Austausch.
* **Typ** `EMERGENCY` **(Reine Warnkanäle):**
  * Behörden/Moderatoren (Power Level 100): Exklusive Schreibrechte für offizielle Warnungen.
  * Bürger (Power Level 0, `m.room.power_levels` restriktiv gesetzt): **Reiner Lesekanal (Muted).** Die Option, Nachrichten zu senden, ist für Bürger in diesem Raumtyp serverseitig gesperrt, um Falschinformationen und Panik in Akutsituationen zu verhindern.