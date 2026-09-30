# Betrieb, Anrufsteuerung und Adapter

## Einrichtung

Die bestehenden Geräteaktionen funktionieren ohne `call_control`. Für die optionale
Steuerung die Dateien [controller.items](../examples/controller.items) und
[controller.rules](../examples/controller.rules) nach openHAB übernehmen, Itemnamen
bei Bedarf anpassen und dieselben Namen in YAML eintragen. Danach
`call_control.enabled: true` setzen und den Container neu starten.
`voice-home doctor` prüft die Items und ihre Typen ausschließlich lesend; es testet
keine Schreibberechtigung durch Gerätebefehle. Der Token benötigt für den Betrieb
Lese-, Ereignis- und Schreibzugriff auf die verwendeten Items.

| YAML-Parameter | Standard / Bedeutung |
| --- | --- |
| `smarthome.adapter` | `openhab`; derzeit einzige Implementierung |
| `call_control.enabled` | `false`; Steuerungsanbindung optional |
| `call_control.initial_accepting` | `true`; Startwert der Annahme bei jedem Prozessstart, auch ohne Anbindung |
| `call_control.switch_item` | Switch für ON/OFF-Befehle und bestätigte Freigabe, `autoupdate="false"` |
| `call_control.status_item` | String für den Betriebsstatus |
| `call_control.call_active_item` | Switch für eine bestätigte, noch nicht beendete SIP-Verbindung |
| `call_control.heartbeat_item` | DateTime für das letzte Lebenszeichen |
| `call_control.heartbeat_interval_seconds` | `10`, positive Zahl; Beispiel-Ausfallregel: nach 30 Sekunden |

Bei aktivierter Anbindung sind vier unterschiedliche, gültige Itemnamen erforderlich.
Bei verändertem Lebenszeichenintervall die 30-Sekunden-Frist der Beispielregel
entsprechend anpassen. Die Items müssen für sich stehen und dürfen keine Gerätekanäle
oder Regeln auslösen, die Türen/Tore bedienen.

## Annahme und Betriebsstatus

Der Controller besitzt den Zustand. openHAB sendet **Commands**, der Controller
bestätigt per **State Update**. Ein gespeicherter Itemzustand oder `postUpdate`
schaltet den Controller nicht um. Wiederholtes ON/OFF ist zulässig.

AUS weist neue zugelassene Anrufe mit SIP 486 ab und verwirft wartende Rückrufe.
Andere Telefone können je nach FRITZ!Box-Rufverteilung weiter klingeln. Bestehende
Gespräche und bereits gewählte ausgehende Rückrufe laufen weiter; weitere
Sprachbefehle bleiben erlaubt. AUS löscht keine Rückrufbudgets. EIN belebt keine
verworfenen Rückrufe wieder. Ein Rückrufauslöser, der während AUS noch auflegt,
darf auch nach schnellem AUS/EIN keinen neuen Rückruf erzeugen.

`CallActive=ON` bedeutet bestätigte SIP-Verbindung, auch während der kurzen
Annahme eines Rückrufauslösers. Nur klingelnde Verbindungen zählen nicht.
`BUSY` umfasst zusätzlich Rückrufpause, Verbindungsaufbau und laufende Aktionen.

Priorität des Betriebsstatus: `OFFLINE` (Beenden), `STARTING` (Initialisierung),
`ERROR` (SIP/Sprachkomponente/Steuerungsadapter gestört), `BUSY`, `DISABLED`, `READY`.
Während eines laufenden Gesprächs können Freigabe OFF und Betriebsstatus BUSY
gleichzeitig zutreffen. Eine einzelne fehlgeschlagene Geräteaktion wird über ihr
Aktionsergebnis gemeldet; der Status ist kein lückenloser Gesundheitsmonitor aller Geräte.

Bei openHAB-Ausfall bleibt die Freigabe erhalten. Automatische Wiederverbindung
mit 1 bis maximal 30 Sekunden Rückwartezeit; beim Wiederverbinden wird der aktuelle
Controllerzustand veröffentlicht. Verpasste Commands werden nicht nachgeholt.
Eigene State Updates lösen keine Commands aus. Lebenszeichen werden nicht weiter
erzeugt, wenn der Controller seit 15 Sekunden keinen aktuellen Zustand geliefert hat.

Ein harter Prozessabbruch kann OFFLINE nicht aktiv senden. Die Beispielregel setzt
nach Ablauf des Lebenszeichens den Status auf OFFLINE sowie Gespräch/Freigabe auf
UNDEF (unbekannt). Restore-on-startup für diese Items nicht als Steuerung verwenden.

## Lokale Abfrage

```bash
docker compose exec controller voice-home status
docker compose exec controller voice-home health
```

`status` liefert JSON: `at`, `fresh`, `age_seconds`, `status`, `accepting`,
`call_active`, `busy`, `registered`, `registration_code`, `speech_ready`,
`adapter_connected`, `dropped_logs`. Ohne aktivierte Steuerungsanbindung ist
`adapter_connected` null; Geräteaktionen verwenden den Adapter trotzdem.
`dropped_logs` zählt lokal verworfene Syslog-Meldungen, keinen bestätigten Empfang.

Der Snapshot liegt ausschließlich unter `/tmp/voice-home/health.json`. Im Container
ist `/tmp` tmpfs. Er wird spätestens alle zwei Sekunden aktualisiert, niemals beim
Start eingelesen. Fehlend, ungültig oder mindestens 15 Sekunden alt bedeutet
UNKNOWN und Exitcode 1; bei veralteten Daten sind aktuelle Zustandsflags null.
Ein frischer Status hat Exitcode 0, auch bei DISABLED oder ERROR. `health` prüft
zusätzlich SIP-Anmeldung und geladene Sprachkomponente. DISABLED ist gesund.
Außerhalb des Containers muss der Betreiber `/tmp` selbst als RAM-Dateisystem bereitstellen.

## Zugangsdaten und Compose

SIP: genau eine Quelle `sip.password` oder `sip.password_file`.
openHAB: wahlweise `openhab.token` oder `openhab.token_file`; beide leer bedeutet
anonymer Zugriff. Zwei nichtleere Quellen werden abgewiesen. Dateien enthalten
jeweils nur den Wert; umgebende Leerzeichen/Zeilenumbrüche werden entfernt.
Relative Dateipfade beziehen sich auf den Ordner der YAML-Datei **im Container**.

Die Basis-Compose-Datei benötigt nur YAML. Dateivariante:

```bash
docker compose -f compose.yaml -f compose.secrets.yaml up -d
```

In dieser Variante `password` durch `password_file` ersetzen und gegebenenfalls
`token_file` setzen. Die Dateien müssen für UID 10001 lesbar sein. Bei unbenutztem
openHAB-Token dessen Einträge aus der Secret-Compose-Vorlage entfernen.

Ohne zusätzliche Docker-Logdateien (Compose >= 2.24.4):

```bash
docker compose -f compose.yaml -f compose.no-container-logs.yaml up -d
```

Die Secret-Variante lässt sich als weitere `-f`-Datei kombinieren. Das YAML-Logziel
separat auf `none`, `file` oder `syslog` stellen. Änderungen an Compose erfordern
ein Neuerstellen des Containers, nicht nur `docker restart`.

## Upgrade von SQLite

Erst ein laufendes Gespräch beenden lassen und den alten Controller stoppen.
Dann mit dem neuen Image ausschließlich die alten Laufzeitdateien entfernen:

```bash
docker compose stop controller
docker compose run --rm --no-deps --entrypoint python controller /app/scripts/remove_legacy_runtime.py
docker compose up -d
```

Das Skript entfernt nur `callbacks.sqlite` samt SQLite-Begleitdateien und die alte
`health.json`/`health.tmp` im Datenverzeichnis. Ansagen und andere Dateien bleiben
erhalten. Kein Löschen des gesamten Volumes und keine Zusage physisch sicherer Löschung.

## Adapter erweitern

`SmartHomeAdapter` definiert `read_item`, `read_state`, `watch_state`,
`send_command`, `watch_commands`, `publish_state`, `check` und `close`.
`ActionExecutor` wertet die normalisierten Zustände aus und erhält die vorhandene
Semantik von Statuszuordnung, Invertierung und echter Gerätebestätigung.
Adapter müssen Metadaten zu Typ und vorhergesagten Zuständen normalisieren,
beobachtete Änderungen mit monotonem Empfangszeitpunkt liefern und Fehler ohne
Zugangsdaten als RuntimeError melden. Explizite Befehlsablehnung wird als
`CommandRejected` unterschieden. Keine SIP-/Sprachänderungen für einen neuen Adapter.
