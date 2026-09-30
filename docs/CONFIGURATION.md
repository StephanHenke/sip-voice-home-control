# Vollständige Konfigurationsreferenz

Stand: 30.09.2026. Diese Referenz beschreibt die implementierten Parameter.
Die Standardwerte stammen aus dem Code; die [Beispiel-YAML](../config.example.yaml)
setzt teilweise ausdrücklich andere Werte. Private Einstellungen gehören in
`config.yaml` beziehungsweise `config.local.yaml`.

Die Pfade gelten innerhalb des Containers. YAML-Änderungen werden beim Start
eingelesen: anschließend validieren und den laufenden Controller neu starten.
Ein Image-Neubau ist für reine Konfigurationsänderungen nicht erforderlich.

## Aufbau und allgemeine Werte

Die obersten Bereiche sind `sip`, `callers`, `dialog`, `callback`, `openhab`,
`speech` und `actions`; hinzu kommen `region` und `data_dir`.

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `region` | `DE` | Region zur Interpretation national geschriebener Rufnummern. Nummern mit Landesvorwahl sind vorzuziehen. |
| `data_dir` | `/data` | Beschreibbares Verzeichnis für Rückrufdatenbank, erzeugte Ansagen und Healthstatus. Details: [Daten und Protokolle](LOGGING_AND_DATA.md). |
| `callers` | `[]` | Liste erlaubter Anrufer. Ohne Einträge wird kein Anrufer zugelassen. |
| `actions` | `[]` | Liste konfigurierter Aktionen. Ohne Einträge gibt es keine ausführbare Geräteaktion. |

Unbekannte oberste Bereiche und unbekannte Felder einer Aktion werden abgewiesen.
Nicht jeder andere Unterbereich prüft unbekannte Schlüssel; Schreibfehler können
dort unbemerkt bleiben. Nur die hier aufgeführten Schlüssel verwenden.
Es gibt keine allgemeinen Umgebungsvariablen zum Überschreiben der YAML-Werte.

## SIP / FRITZ!Box

| Parameter | Standard | Bedeutung und Werte |
| --- | --- | --- |
| `sip.host` | Pflicht | IPv4-Adresse der FRITZ!Box. Registrar und erlaubte Netzwerkquelle eingehender Anrufe. |
| `sip.username` | Pflicht | SIP-Benutzername; Buchstaben, Ziffern, `_`, `.`, `-`. |
| `sip.password_file` | Pflicht | Pfad zur Datei mit dem SIP-Passwort, z. B. `/run/secrets/sip_password`. Inhalt muss beim SIP-Start vorhanden und nicht leer sein. |
| `sip.port` | `5060` | SIP-Port der FRITZ!Box. |
| `sip.local_port` | `5062` | Lokaler SIP-Port des Controllers. |
| `sip.transport` | `udp` | `udp` oder `tcp`; betrifft SIP-Signalisierung, nicht den RTP-Audiotransport. |
| `sip.rtp_port` | `40000` | Beginn des lokalen Medienportbereichs; zusätzlich werden zehn Ports berücksichtigt, also im Standard `40000–40010/UDP`. |
| `sip.public_address` | nicht gesetzt | Optional: im SIP-/Medienaufbau angekündigte, erreichbare IPv4-Adresse des Hosts, etwa bei NAT. |
| `sip.controller_number` | nicht gesetzt | Eigene externe Controller-Rufnummer. Verhindert, dass dieselbe Nummer als erlaubter Rückrufempfänger eingetragen wird. Die eigentliche Rufnummernzuweisung erfolgt in der FRITZ!Box. |

Die drei Portwerte müssen ganze Zahlen von `1024` bis `65520` sein.
SIP-Weiterleitungen und Transfers sind nicht freigegeben. Die getestete
Docker-Desktop-Anbindung verwendet TCP; die Compose-Vorlage ist für Linux mit
Host-Netzwerk gedacht. Weitere Hinweise stehen im [Schnellstart](../README.md).

## Erlaubte Anrufer

Jeder Eintrag in `callers` enthält:

| Parameter | Standard | Bedeutung und Werte |
| --- | --- | --- |
| `callers[].number` | Pflicht | Vollständige Telefonnummer, z. B. `"+4915123456789"`. Wird normalisiert; nationale Schreibweise nutzt `region`. Im Rückrufmodus ist dies zugleich das feste Rückrufziel. |
| `callers[].name` | Pflicht | Begrüßungsname, nicht leer und höchstens 80 Zeichen. Wird auch in einer gespeicherten TTS-Ansage gesprochen. |
| `callers[].access_mode` | `callback` | `callback`: Anruf beenden und gespeicherte Nummer zurückrufen. `direct`: erlaubten Anruf direkt annehmen und Dialog starten. |

Normalisierte Nummern müssen eindeutig sein. Alle erlaubten Anrufer können alle
aktivierten Aktionen verwenden; individuelle Aktionsrechte pro Person sind
derzeit nicht implementiert. Name und Rufnummer werden nicht aus dem SIP-Anzeigenamen
übernommen. Details zur Reichweite des Rückrufschutzes: [Anforderungen](REQUIREMENTS.md).

## Gespräch und Wartezeiten

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `dialog.answer_delay_ms` | `1000` | Zusätzliche Pause vor der ersten Begrüßung, sobald Gespräch und Audiokanal bereit sind. `0` deaktiviert diese Pause. Folgeansagen warten nicht erneut. |
| `dialog.listen_timeout_seconds` | `15` | Antwortfenster nach dem Signalton, bis ein Audiobeginn als Sprache gewertet wird. Gilt auch für Bestätigungs- und Folgefragen. |
| `dialog.max_utterance_seconds` | `15` | Maximale Zeit ab erkanntem Sprechbeginn; wird durch weiteres Sprechen nicht immer wieder verlängert. |
| `dialog.max_failures` | `2` | Maximale Zahl aufeinanderfolgender Verständnisfehler bzw. abgelaufener Antwortfristen, danach Abschied. Ganze Zahl größer `0`. |
| `dialog.max_call_seconds` | `120` | Maximale Gesprächsdauer ab bestätigtem Gesprächsaufbau; umfasst auch Ansagen und die Wartezeit auf Aktionen. |

Zeitwerte müssen endlich und positiv sein; nur `answer_delay_ms` darf `0` sein.
Die Erkennung wird vor dem Signalton vorbereitet. Ein Geräusch ohne erkannten
Text zählt nicht als Verständnisfehler und verlängert nicht das ursprüngliche
Antwortfenster. Lautstärkeaktivität allein ist noch kein verstandener Befehl.

## Rückruf

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `callback.trigger_mode` | `reject` | `reject`: ursprünglichen Anruf mit SIP 603 abweisen. `answer_hangup`: kurz annehmen, bestätigten Verbindungsaufbau abwarten, sofort auflegen, anschließend zurückrufen. |
| `callback.delay_ms` | `3000` | Pause nach Beendigung des ursprünglichen Anrufs bis zum Rückruf; `0` ist erlaubt. |
| `callback.ring_timeout_seconds` | `30` | Höchstdauer bis zum bestätigten Verbindungsaufbau. Begrenzt insbesondere das Klingeln beim Rückruf; der Adapter verwendet sie allgemein für noch nicht bestätigte Anrufe. |
| `callback.cooldown_seconds` | `60` | Mindestabstand zwischen zugelassenen Rückrufversuchen derselben Nummer. |
| `callback.max_attempts_per_number_per_hour` | `5` | Höchstzahl zugelassener Rückrufversuche pro Nummer in den letzten 3600 Sekunden, keine feste Uhrzeit-Stunde. Ganze Zahl größer `0`. |

Zeitwerte müssen endlich und positiv sein; nur `delay_ms` darf `0` sein.
Fehlgeschlagene Rückrufe zählen als Versuch. Es gibt keine automatische
Wahlwiederholung, keinen Ersatz durch Direktannahme und keine Warteschlange.
Ein Gespräch oder ausstehender Rückruf belegt den einzigen Gesprächsplatz.
Die Limits bleiben durch SQLite über Neustarts erhalten. Direkte Anrufe verwenden
diese Rückruflimits nicht. `answer_hangup` kann tarifabhängig als angenommener
Anruf berechnet werden.

## openHAB

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `openhab.base_url` | `http://openhab:8080` | Basis-URL mit `http` oder `https` und Hostname/IP. Keine Zugangsdaten, Abfrageparameter oder URL-Fragmente in die URL schreiben. |
| `openhab.token_file` | `""` | Datei mit API-Token. Bei leerem Wert wird ohne Bearer-Token gearbeitet; das muss openHAB erlauben. Die Beispiel-YAML setzt `/run/secrets/openhab_token`. |

Der Controller liest Item-Zustände und Ereignisse und sendet einzelne REST-Befehle.
Ein HTTP-Erfolg allein ist keine Bestätigung der Gerätebewegung. Der Befehl wird
nicht automatisch wiederholt. Verbindungs- und Ereignisfehler können zum Ergebnis
„nicht bestätigt“ führen, auch wenn openHAB den Befehl bereits erhalten hat.

## Spracherkennung und Sprachausgabe

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `speech.asr_model` | `/models/vosk-model-small-de-0.15` | Verzeichnis des lokalen Vosk-Sprachmodells. |
| `speech.tts_model` | `/models/de_DE-thorsten-medium.onnx` | Piper-Stimmmodell. Daneben muss die zugehörige Datei mit zusätzlicher Endung `.json` liegen. |
| `speech.command_vocabulary` | `true` | Wortschatz aus Aktionsaliasen/-mustern plus Verneinungen, Dialog- und Kontextwörtern. Ein uneingeschränkter Erkenner prüft zusätzlich Verneinungen, Ja-Antworten und widersprüchliche bekannte Aktionen. `false`: nur uneingeschränkte Erkennung. |
| `speech.min_confidence` | `0.85` | Mindestkonfidenz von `0` bis `1`, einschließlich Grenzen. Es zählt grundsätzlich das unsicherste erkannte Wort; zusätzliche Gegenprüfungen können Ergebnisse verwerfen. Keine kalibrierte Fehlerwahrscheinlichkeit. |
| `speech.end_silence_ms` | `700` | Manuelle Auswertung nach dieser Pause seit letzter Lautstärkeaktivität; Bereich `300–2000` ms. Vosk kann selbst schon vorher ein Satzende melden. |

Ein vollständiges erkanntes Sprachmuster muss passen; es gibt keinen unscharfen
Teilstring-Abgleich. „Bitte“ ist automatisch an Wortgrenzen zugelassen.
Umlaute und Groß-/Kleinschreibung werden beim Textvergleich normalisiert.
Ein angepasstes Wörterbuch ersetzt keinen realen Test der verwendeten Stimmen.
Neue Aliaswörter müssen auch zum verwendeten Vosk-Modell passen.

## Aktionen

Alle folgenden Felder gehören zu einem Eintrag in `actions`.

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `actions[].id` | Pflicht | Eindeutige Kennung: Kleinbuchstabe, danach Kleinbuchstaben, Ziffern oder `_`. Wird in Aktionsprotokollen ausgegeben. |
| `actions[].aliases` | Pflicht | Nichtleere Liste von Zielbezeichnungen, z. B. `[Haustür, Tür]`. |
| `actions[].patterns` | Pflicht | Nichtleere Liste vollständiger Satzmuster, jedes mit genau einem `{target}`. Keine weiteren Platzhalter. |
| `actions[].enabled` | `false` | Nur `true` aktiviert die Geräteaktion. Ein erkanntes deaktiviertes Ziel führt zur Ansage, dass die Aktion noch nicht eingerichtet ist. |
| `actions[].command_item` | `""` | openHAB-Item für den Befehl; bei aktivierter Aktion Pflicht. |
| `actions[].command` | `""` | Zu sendender Text, bei aktivierter Aktion Pflicht, z. B. `"UP"`, `"DOWN"`, `"ON"` oder `"3"`. Numerische Befehle in Anführungszeichen schreiben. |
| `actions[].feedback_item` | `""` | Item mit tatsächlichem Gerätestatus; bei aktivierter Aktion Pflicht. Darf dem Befehls-Item entsprechen, siehe unten. |
| `actions[].feedback_mode` | `state` | `state`: Rohwerte bzw. benannte Zustände. `rollershutter_opening`: gemessene Prozentbewegung in Richtung `open_position`. |
| `actions[].state_values` | `{}` | Zuordnung selbst gewählter Zustandsnamen auf nichtleere Listen von Rohwert-Strings, z. B. `closed: ["1"]`. Namen: Kleinbuchstabe, danach Kleinbuchstaben, Ziffern oder `_`. Jeder Rohwert darf nur einem Zustand zugeordnet sein. |
| `actions[].success_states` | `[]` | Benannte Erfolgszustände aus `state_values`, z. B. `[opening, open]` oder `[closed]`. |
| `actions[].failure_states` | `[]` | Benannte Fehlerzustände aus `state_values`, z. B. `[blocked]`. |
| `actions[].success_values` | `[]` | Alternative zu benannten Zuständen: direkte Erfolgswerte als Strings, z. B. `["OPEN"]`. |
| `actions[].failure_values` | `[]` | Direkte Fehlerwerte als Strings. |
| `actions[].open_position` | `0` | Offene Prozentposition im Modus `rollershutter_opening`, zwischen `0` und `100`. |
| `actions[].closed_position` | `100` | Geschlossene Prozentposition im selben Modus, zwischen `0` und `100`, verschieden von `open_position`. Vertauschen invertiert die Auswertung. |
| `actions[].timeout_seconds` | `10` | Wartefrist auf Rückmeldung ab Befehlsversand: größer `0`, höchstens `60` Sekunden. Für bestätigte vollständige Garagenschließung setzt das Beispiel `45`. |
| `actions[].success_text` | `"OK."` | Ansage bei bestätigtem Erfolg. Es folgt automatisch „Möchtest du noch etwas?“. Der Text sollte zur tatsächlich geprüften Rückmeldung passen. |
| `actions[].require_confirmation` | `false` | Bei `true` erst nach Bestätigungsfrage und erkanntem explizitem „Ja“/„Ja bitte“ ausführen. |
| `actions[].confirmation_text` | `""` | Eigener vollständiger Fragetext. Pflicht und nicht leer, wenn `require_confirmation: true`. |

Zusammenhänge:

- Für aktivierte Aktionen dürfen Item-Namen mit Buchstaben oder `_` beginnen;
  danach sind Buchstaben, Ziffern und `_` erlaubt.
- Benannte Zustände und direkte Erfolgs-/Fehlerwertelisten nicht mischen.
  Erfolg und Fehler müssen disjunkt sein. `NULL` und `UNDEF` sind nie Erfolgswerte.
- Im Modus `state` braucht eine aktivierte Aktion mindestens einen Erfolgswert.
  Ein vor dem Befehl bereits vorhandener Erfolg wird nicht durch unveränderte
  Wiederholung zu einem neuen Erfolg. Auch Wechsel zwischen Rohwerten desselben
  benannten Zustands reichen nicht.
- Bei einem gemeinsamen Befehls-/Rückmelde-Item muss dessen openHAB-Metadatum
  `autoupdate` ausdrücklich `false` sein. Andernfalls kann der Befehl gesendet
  werden, aber es folgt keine bestätigte Erfolgsansage.
- `rollershutter_opening` verlangt ein tatsächliches `Rollershutter`-Item und
  erkennt eine neue Bewegung näher zu `open_position`. Es darf nicht mit
  `state_values`, `success_states`, `failure_states` oder `success_values`
  kombiniert werden; direkte `failure_values` sind möglich. Zulässige Befehle
  sind `UP`, `DOWN` oder eine Prozentposition als String. Die Richtung der
  Erfolgsprüfung bleibt unabhängig davon **zur offenen Position**.
- Einen Modus `rollershutter_closing` gibt es nicht. Die Garagenschließung im
  Beispiel verwendet `state` und den tatsächlichen Status `closed`.
- Die Werte `open_position`/`closed_position` dürfen außerhalb des
  Rollershutter-Modus nicht von ihren Standards abweichen.
- Sprachmuster verschiedener Aktionen dürfen nach Normalisierung nicht
  kollidieren. Dasselbe Ziel darf eigene, unterschiedliche Öffnen-/Schließen-Muster haben.

Beispiele für Statuszuordnung, Invertierung, dasselbe Item sowie Öffnen und
Schließen stehen in [Geräte konfigurieren](DEVICE_CONFIGURATION.md).
Alle Ansagen zeigt das [Gesprächsdiagramm](CALL_FLOW.md).

## Kommandozeile

`voice-home [--config PFAD] BEFEHL`; `--config` steht vor dem Unterbefehl.
Standardpfad: `/config/config.yaml`. `-h`/`--help` zeigt die jeweilige Hilfe.

| Befehl / Argument | Wirkung |
| --- | --- |
| `validate` | YAML und Sprachmuster prüfen; Anzahl von Anrufern, Aktionen und Mustern ausgeben. Keine Verbindungen; prüft nicht, ob alle Secret-/Modelldateien vorhanden und nutzbar sind. |
| `parse TEXT` | Einen übergebenen Text offline zuordnen; gibt Art und ggf. Aktionskennung aus. Prüft nicht, ob eine so erkannte Aktion aktiviert ist. |
| `doctor` | openHAB und konfigurierte Items aktivierter Aktionen lesend prüfen; keine Gerätebefehle. |
| `register --seconds 15` | SIP-Registrierung zeitlich begrenzt testen; `--seconds` hat Standard `15`. Eingehende Anrufe werden abgelehnt, kein Sprachdialog oder Rückruf. Nicht parallel mit derselben SIP-Konfiguration betreiben. |
| `serve` | Normalbetrieb starten. |
| `health` | Gespeicherten Healthstatus lesen. Erfolg nur bei Meldung jünger als 15 Sekunden, SIP-Anmeldung und geladener Sprachkomponente; keine Prüfung der Erkennungsqualität. |

## Docker Compose und feste Werte

Diese Einstellungen stehen in [compose.yaml](../compose.yaml), nicht in der
Anwendungs-YAML. Service-Name: `controller`.

| Compose-Einstellung | Wert der Vorlage / Bedeutung |
| --- | --- |
| `build`, `image` | `.` und `sip-voice-home-control:local`; Image aus dem Projekt bauen. |
| `restart`, `init` | `unless-stopped` und `true`; Prozessneustart und Init-Prozess. Ein bloßes `unhealthy` löst keinen automatischen Neustart aus. |
| `network_mode` | `host`, für natives Linux. Docker Desktop benötigt die in README beschriebene eigene Port-/Adresskonfiguration. |
| `read_only`, `cap_drop`, `security_opt` | `true`, `[ALL]`, `[no-new-privileges:true]`. |
| `mem_limit`, `cpus` | `2g`, `2`. |
| `tmpfs` | `/tmp:size=64m,mode=1777`; flüchtiges temporäres Dateisystem. |
| `volumes` | `./config.yaml` schreibgeschützt nach `/config/config.yaml`; benanntes Volume `controller-data` nach `/data`. Bei Änderung von `data_dir` die Einbindung anpassen. |
| `secrets` | Dateien `./secrets/sip_password` und `./secrets/openhab_token` nach `/run/secrets/…`. Dateien müssen für Container-UID `10001` lesbar sein. |
| `healthcheck.test` | `[CMD, voice-home, health]`. |
| `healthcheck.interval`, `timeout`, `start_period`, `retries` | `15s`, `5s`, `180s`, `3`. |
| `logging.options.max-size`, `logging.options.max-file` | `10m`, `"3"`; vom Docker-Logging-Treiber umgesetzte Dateirotation. Kein Löschalter in Tagen. Details: [Protokolle](LOGGING_AND_DATA.md). |

Im Dockerfile sind Container-UID `10001` und der Build-Parameter
`PJSIP_VERSION=2.16` festgelegt. Die Modelle werden beim Build heruntergeladen.
`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` und `PYTHONUNBUFFERED=1` sind dort
Laufzeitvorgaben, keine Anwendungs-YAML-Parameter.

Derzeit ebenfalls nicht über YAML einstellbar: feste deutsche Standardansagen
außer Name/Erfolg/Bestätigungsfrage, ein gleichzeitiger Gesprächsplatz,
Codec-Reihenfolge G.722 → PCMA → PCMU, 16-kHz-Mono-Verarbeitung,
Lautstärkeschwelle 250, 250-ms-Pause vor dem Signalton und dessen 80-ms-Dauer.
Es gibt keine YAML-Parameter für Log-Level, Gesprächsaufzeichnung oder
automatisches Löschen alter TTS-Ansagen.
