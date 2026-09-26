# Mitwirken am POLARIS Geofencing-Gateway

Vielen Dank, dass du zu POLARIS beitragen möchtest! Als dezentrales, digital souveränes Bürgernetzwerk legen wir höchsten Wert auf Codequalität, Datenschutz (Privacy by Design) und Lizenzkonformität.

## 🤖 Richtlinien für die Nutzung von KI-Assistenten

Die Nutzung von KI-Tools (wie Google Gemini, GitHub Copilot, ChatGPT etc.) zur Unterstützung bei der Entwicklung ist ausdrücklich erlaubt, unterliegt jedoch strengen Qualitäts- und Transparenzregeln:

1. **Keine blinde Übernahme:** KI-generierter Code darf nicht ungesehen committet werden. Du musst den Code vollständig verstehen, manuell nachbearbeiten und lokal testen.
2. **Besonderheit bei Python & Rust:**
   * **Python (/prototype/):** Achte penibel auf Typ-Handling und flüchtige RAM-Zuweisungen. KI neigt hier zu versteckten Laufzeitfehlern.
   * **Rust (/production/):** Nutze die Strenge des Compilers. Code, der den Borrow Checker nur durch `unsafe`-Blöcke umgeht, die von einer KI vorgeschlagen wurden, wird nicht akzeptiert.
3. **Lizenzkonformität:** Stelle sicher, dass die KI keine urheberrechtlich geschützten Code-Snippets ausspuckt, die gegen die MIT-Lizenz dieses Projekts oder Drittlizenzen verstoßen.
4. **Transparenz:** Bitte deklariere im Pull Request (PR) kurz, ob und an welchen Stellen KI-Unterstützung genutzt wurde.

## 🚀 Wie du einen Beitrag einreichst

1. **Issue erstellen oder wählen:** Besprich größere Änderungen vorab in einem Issue.
2. **Repository forken:** Erstelle einen eigenen Branch für deine Änderungen.
3. **Code-Qualität einhalten:** 
   * Verwende für Python `black` / `flake8`.
   * Verwende für Rust `cargo fmt` und `cargo clippy`.
4. **Pull Request öffnen:** Beschreibe deine Änderungen klar und füge den KI-Hinweis hinzu, falls zutreffend.

Gemeinsam bauen wir eine sichere und transparente digitale Daseinsvorsorge!
