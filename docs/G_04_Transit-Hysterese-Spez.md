# POLARIS-Gateway - Transit- und Hysterese-Spezifikation

* **Projekt-ID:** matrix-polaris
* **Komponente:** matrix-polaris-gateway (Algorithmic Routing Layer)
* **Version:** 1.0.0 (Soll-Spezifikation)
* **Lizenz:** MIT-Lizenz (Open Source)
* **Status:** ARCHITECTURAL SPECIFICATION (Konzeptionelles Regelwerk; mathematische Logik für die zukünftige Implementierung im Gateway-Modul definiert)

---

## 1. Das Transit-Problem bei hoher Geschwindigkeit

Wenn sich Nutzer in schnellen Fortbewegungsmitteln (z. B. in Zügen oder auf Autobahnen) durch das Versorgungsgebiet bewegen, führt dies bei einer reinen GPS-Punkt-in-Polygon-Abfrage zu folgendem Problem:

* Der Nutzer durchquert in wenigen Minuten zahlreiche hyperlokale Ortsteile (Subzonen).
* Dies würde im Minutentakt automatische Beitritts- und Austrittsbefehle (`join` / `leave`) auf dem Matrix-Homeserver auslösen.
* Diese hohe Frequenz an Raumwechseln erzeugt durch die kryptografischen Berechnungen und Event-Zuweisungen auf dem Homeserver eine erhebliche, unkritische Systemlast (*State Resolution Storms*).
* Für den Nutzer bietet der sekundenweise Beitritt zu einem Ortsteil, den er nur durchfährt, keinen informationellen Mehrwert.

---

## 2. Der geschwindigkeits-adaptive Transit-Filter

Um die Systemlast zu minimieren, implementiert die Architektur des POLARIS-Gateways einen geschwindigkeits-abhängigen Filter auf Basis der vom Endgerät gelieferten Bewegungsdaten (`velocity_kmh`).

### Das Filter-Regelwerk:

* **Modus A: Fußgänger / Nahbereich (**`velocity_kmh < 30.0`**)**
  * Volle Kaskade aktiv. Der Nutzer wird sowohl der übergeordneten Hauptzone (Gemeinde) als auch der spezifischen Subzone (Ortsteil) zugewiesen.
* **Modus B: Regionaler Transit (**`30.0 <= velocity_kmh < 80.0`**)**
  * Eingeschränkte Kaskade. Die Zuweisung zu hyperlokalen Subzonen (Ortsteilen) wird blockiert. Der Nutzer wird ausschließlich der übergeordneten Hauptzone (Gemeinde) zugewiesen.
* **Modus C: Fern-Transit (**`velocity_kmh >= 80.0`**)**
  * Minimale Kaskade. Der Nutzer wird aus allen Sub- und Hauptzonen herausgehalten und temporär ausschließlich der übergeordneten Landkreis-Zone zugewiesen. Die Last auf kommunaler Ebene sinkt dadurch um schätzenswerte 95 %.

---

## 3. Der Hysterese-Schutz (Signal-Stabilisierung)

An den Rändern von geografischen Zonen sowie in Gebieten mit schlechtem GPS-Empfang neigen Koordinaten zum „Springen“ (Signalschwankungen). Um zu verhindern, dass ein Nutzer an einer Zonengrenze permanent zwischen zwei Räumen hin- und hergewechselt wird, definiert das Protokoll eine zeitliche Hysterese (Karenzzeit) für Austrittsbefehle.

### Ablauf des Hysterese-Schutzes:

1. **Sofortiger Beitritt (**`join`**):** Betritt ein Nutzer eine neue Zone, erfolgt der Raumschnitt und der Beitrittsbefehl sofort und ohne Verzögerung.
2. **Verzögerter Austritt (**`leave`**):** Verlässt ein Nutzer eine Zone, wird der `leave`-Befehl nicht sofort ausgeführt.
   * Das Gateway trägt die `user_id` und die verlassene Zonen-ID mit einem aktuellen Zeitstempel in die Zustandstabelle `exit_pending_users` ein.
   * Der endgültige Austritt wird erst vollzogen, wenn sich der Nutzer **10 Minuten (600 Sekunden) ununterbrochen außerhalb der Zone** aufgehalten hat.
   * Kehrt der Nutzer innerhalb dieser 10 Minuten in die Zone zurück, wird der Lösch-Timer verworfen. Der Nutzer bleibt durchgehend im Raum, ohne dass ein neuer kryptografischer Join berechnet werden musste.

---

## 4. Priorisierter Krisen-Override (`STRICT OVERRIDE`)

Das System sieht eine architektonische Ausnahme für den Katastrophen- und Krisenfall vor. Liegt für eine geografische Zone (Haupt- oder Subzone) ein aktives Warn-Event vor (in der Tabelle `polaris_spaces` als Typ `EMERGENCY` markiert), werden der Transit-Filter und der Hysterese-Schutz für diese Zone augenblicklich außer Kraft gesetzt.

* **Logik:** Unabhängig von der aktuellen Reisegeschwindigkeit (selbst bei > 200 km/h im Fernverkehr) erzwingt das Gateway beim Durchqueren des betroffenen Polygons den sofortigen Beitritt zum Krisenraum.
* **Ziel:** Sicherstellung, dass Bürger im Gefahrenbereich (z. B. bei einer akuten lokalen Schadenslage) die offiziellen behördlichen Warnungen ohne Latenz und Einschränkung empfangen.