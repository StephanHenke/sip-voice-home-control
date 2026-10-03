# Sicherheitsrichtlinie

## Unterstützte Versionen

Sicherheitskorrekturen werden für den aktuellen Stand auf `main` und
die daraus veröffentlichten Container-Images bereitgestellt.
Ältere Versionen erhalten keine separaten Sicherheitsupdates.

Bei Fehlermeldungen bitte den Commit, Image-Tag oder Image-Digest
angeben. Der Tag `latest` allein identifiziert keine feste Version.

## Sicherheitslücken melden

Bitte Sicherheitslücken vertraulich über GitHub melden:

https://github.com/StephanHenke/sip-voice-home-control/security/advisories/new

Keine öffentlichen Issues mit ausnutzbaren Details, Zugangsdaten,
Telefonnummern, Gesprächsaufnahmen oder unbereinigten Logs erstellen.

Eine hilfreiche Meldung enthält:
- betroffene Version und Installationsart;
- Beschreibung und mögliche Auswirkungen;
- nachvollziehbare Schritte zur Reproduktion;
- bereinigte Diagnoseinformationen, soweit erforderlich.

Tests ausschließlich an eigenen oder ausdrücklich freigegebenen
Systemen durchführen. Reale Tür- und Toraktionen vermeiden.

Meldungen werden geprüft und notwendige Rückfragen sowie eine
abgestimmte Veröffentlichung angestrebt. Feste Reaktions- oder
Behebungsfristen werden nicht zugesagt.

## Umfang und Sicherheitsziele

Diese Richtlinie umfasst Anwendung, Weboberfläche, SIP-Verarbeitung,
Smart-Home-Adapter, Konfiguration und Bereitstellungsskripte.

Besonders schützenswert sind Zugangsdaten, erlaubte Rufnummern,
Konfigurationsdateien und die Berechtigung zur Gerätebetätigung.

Folgende Eigenschaften müssen erhalten bleiben:
- Gerätebefehle erfordern einen zulässigen Anruf und eine konfigurierte,
  freigegebene Aktion.
- Aktivierte Bestätigungsfragen dürfen nicht umgangen werden.
- Rückrufe verwenden die konfigurierte Zielnummer.
- Die Webverwaltung verlangt eine gültige Anmeldung; ohne gesetztes
  Passwort bleibt der Login gesperrt.
- Webpasswörter werden ausschließlich als gesalzene Hashes gespeichert.
- Geheimnisse dürfen nicht in regulären Logs oder Fehlermeldungen erscheinen.
- Nicht vertrauenswürdige Eingaben dürfen keine beliebigen Befehle,
  Dateizugriffe oder zusätzlichen Geräteaktionen ermöglichen.

Diese Punkte beschreiben Sicherheitsanforderungen, keine Zusicherung
der Fehlerfreiheit.

## Sicherer Betrieb und Grenzen

Die Weboberfläche gehört in ein geschütztes Verwaltungsnetz und sollte
nicht direkt öffentlich erreichbar sein. Ein eigenes starkes Passwort,
HTTPS und eingeschränkte Netzwerkzugriffe verwenden.

Eine erlaubte Rufnummer allein ist kein sicherer Identitätsnachweis.
Der optionale Rückruf an eine fest konfigurierte Nummer verhindert,
dass eine gefälschte Caller-ID allein den direkten Zugriff ermöglicht.
Er schützt nicht gegen kompromittierte Endgeräte, übernommene
Telefonanschlüsse oder Rufumleitungen.

Spracherkennung kann Befehle falsch verstehen. Für sensible Aktionen
Bestätigungsfragen konfigurieren und die Geräteanbindung vor Ort prüfen.
Mechanische Schutzfunktionen und alternative Zugangsmöglichkeiten
bleiben erforderlich.

Administrativer Zugriff auf Host, Container, YAML oder Smart-Home-System
ist eine Vertrauensgrenze: Wer diese Systeme kontrolliert, kann auch
Freigaben und Geräteaktionen verändern.

Konfigurationen, Sicherungen und YAML-Versionen können persönliche Daten
und direkt eingetragene Zugangsdaten enthalten und müssen geschützt werden.
Rückruflimits liegen im RAM und beginnen nach einem Neustart neu.

## Bewertung von Meldungen

Relevant sind insbesondere unberechtigte Geräteaktionen, Umgehung
von Anmeldung oder Bestätigung, Offenlegung von Geheimnissen,
Codeausführung und praktisch erreichbare Dienstblockaden.

Auswirkungen und tatsächlich erforderliche Zugriffsrechte werden
gemeinsam bewertet. Es werden keine pauschalen Schwachstellenklassen
von der Prüfung ausgeschlossen.

## Weitere Informationen

- [Weboberfläche](docs/WEB_UI.md)
- [Protokolle und gespeicherte Daten](docs/LOGGING_AND_DATA.md)
- [Abnahmecheckliste](docs/ACCEPTANCE.md)
- [Lizenz](LICENSE)
