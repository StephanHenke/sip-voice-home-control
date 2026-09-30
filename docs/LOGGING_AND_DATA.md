# Protokolle und gespeicherte Daten

Stand: 30.09.2026. Beschrieben ist der normale Start mit `voice-home serve`.
Die [Parameterreferenz](CONFIGURATION.md) erklärt die zugehörigen Einstellungen.

## Was im Normalbetrieb protokolliert wird

Python schreibt Ereignisse mit Zeitstempel und Schweregrad nach stderr; Docker
erfasst die Prozessausgaben. Die Anwendung setzt das Log-Level auf `INFO`.
Die folgenden Ereignisse enthalten insbesondere:

| Ereignis | Inhalt |
| --- | --- |
| `sip_registration` | SIP-Antwortcode, Anmeldung aktiv ja/nein. |
| `sip_incoming` | Netzwerkadresse und Port des SIP-Gegenübers, üblicherweise FRITZ!Box; `caller_allowed` ja/nein. |
| `sip_call` | Verbindungszustand und letzter SIP-Statuscode. |
| `sip_rejected` | Grund: Registrierungsprobe, nicht erlaubte Quelle/Nummer oder belegter Gesprächsplatz. |
| `callback_rate_limited` | Rückruflimit erreicht. |
| `callback_trigger_accepted`, `callback_started`, `callback_failed` | Annahme des Rückrufauslösers und Start bzw. Fehlschlag des Rückrufs. |
| `dialog_listening` | Dialogzustand und konfiguriertes Antwortfenster. |
| `dialog_response_timeout` | Dialogzustand und ob bereits Sprechbeginn erkannt wurde. |
| `speech_empty_result` | Leeres Erkennungsergebnis wurde ignoriert. |
| `speech_audio_overflow` | Audioverarbeitung kam mit dem begrenzten Puffer nicht nach. |
| `action_requested` | Konfigurierte Aktionskennung, z. B. `garage_close`. |
| `action_result` | Aktionskennung und Ergebnis `ok`, `failed`, `unconfirmed` oder `disabled`. |
| Konfigurations-/Dateifehler | Die CLI gibt die Fehlerklasse aus, nicht die komplette Konfiguration oder das Secret. |

**Auch HTTP-Zugriffe können protokolliert werden.** Die verwendete HTTP-Bibliothek
`httpx` schreibt auf INFO-Ebene Methode, vollständige URL und Antwortstatus.
Dadurch können die openHAB-Adresse, private Item-Namen und Ereignisfilter in
Logzeilen stehen. Das Request-Log enthält standardmäßig keine Authorization-Header
oder Request-/Response-Bodies. Bei realen Tests wurden diese HTTP-Logzeilen beobachtet.

Beispiel mit Platzhaltern:

```text
INFO action_requested id=garage_close
INFO HTTP Request: POST http://openhab:8080/rest/items/GarageDoor "HTTP/1.1 200 OK"
INFO action_result id=garage_close result=ok
```

PJSIP und die Sprachbibliotheken können zusätzliche technische Start-, Warn-
und Fehlermeldungen ausgeben. PJSIP läuft nach Initialisierung mit Log-Level 1,
vollständiges SIP-Message-Logging ist ausgeschaltet. Vor dem Teilen von Logs
trotzdem alle Zeilen prüfen; die Anwendung verspricht keine umfassende
Anonymisierung aller Bibliotheksmeldungen.

Die ausdrücklich implementierten Betriebsereignisse enthalten keine
Anrufernamen, vollständigen Anrufernummern, gesprochenen Texte, Wortkonfidenzen
oder Passwörter. Aktionskennungen, Zeitpunkte, Netzwerkadressen und über HTTP-URLs
sichtbare Item-Namen lassen jedoch Rückschlüsse auf die Nutzung zu.
Es gibt keine eindeutige Gesprächs-ID oder vollständige Zuordnung einer Aktion
zu einer Person im normalen Anwendungslog.

## Was nicht als Gesprächsprotokoll gespeichert wird

Der normale SIP-Adapter schreibt weder eingehende Audioaufnahmen noch
Erkennungstexte in Dateien. Audioframes, Erkennungstext und Wortkonfidenzen werden
während der Verarbeitung im Arbeitsspeicher verwendet. Die Eingangsqueue umfasst
höchstens 100 Frames zu 20 ms; zusätzlich hält der Erkenner internen Zustand.
Das ist keine zugesicherte Gesamtgrenze des Speicherverbrauchs.

Die vorhandenen WAV-Dateien im Datenvolume sind **erzeugte Ansagen**, keine
Gesprächsmitschnitte. Insbesondere kann darin „Hallo {Name}“ hörbar sein.

## Dateien, Inhalte und Aufbewahrung

Mit dem Standard `data_dir: /data` entstehen folgende Daten:

| Ort | Inhalt und Zweck | Aufbewahrung |
| --- | --- | --- |
| `config.yaml` / `config.local.yaml` auf dem Host | SIP-Benutzername, Adressen, erlaubte Rufnummern und Namen, Item-Zuordnungen, Einstellungen. | Bis zur manuellen Änderung/Löschung; keine automatische Bereinigung. |
| `secrets/` auf dem Host, im Container `/run/secrets/` | SIP-Passwort und ggf. openHAB-Token als Dateiinhalte. | Bis zur manuellen Änderung/Löschung. Normale Compose-Secret-Dateien sind kein verschlüsselter Tresor. |
| `/data/callbacks.sqlite` | Tabelle `attempts`: vollständige normalisierte Rufnummer in `number`, Unix-Zeitstempel in `at`. Dient Sperrfrist und stündlichem Rückruflimit. | Einträge älter als 24 Stunden werden erst beim nächsten Aufruf der Rückrufreservierung gelöscht. Ohne neue Rückrufprüfung bleiben sie länger stehen. Keine zeitgesteuerte Löschung und keine Zusage sicherer physischer Datenlöschung. |
| `/data/prompts/<hash>.wav` | Lokal erzeugte TTS-Begrüßungen, Erfolgs-, Bestätigungs- und übrige Ansagen. Dateiname ist ein Hash, der hörbare Inhalt kann Namen enthalten. | Keine automatische Ablaufzeit. Bei geänderten Namen/Texten/Stimmmodellen entstehen neue Dateien; alte bleiben liegen. |
| `/data/prompts/ready.wav` | Generierter Signalton. | Bleibt im Datenvolume; wird beim Start erzeugt/überschrieben. |
| `/data/health.json` | Letzter Zeitstempel `at`, `registered`, `registration_code`, `speech_ready`, `busy`. Keine Personen- oder Gesprächsinhalte. | Etwa alle zwei Sekunden atomar überschrieben, kein Verlauf. Auch beim Beenden aktualisiert. |
| Temporäre Dateien, z. B. `/tmp` | Temporäre Bibliotheksdaten; im normalen Betrieb keine Gesprächsaufzeichnung. Unvollständige TTS-Erzeugung kann zusätzlich `.tmp.wav` im Ansagenverzeichnis hinterlassen. | `/tmp` ist in der Vorlage flüchtiges tmpfs; das persistente Ansagenverzeichnis wird nicht automatisch bereinigt. |
| Docker-Protokoll | stdout/stderr einschließlich der oben beschriebenen Ereignisse und Bibliotheksmeldungen. | Rotation nach Größe, siehe unten. |
| `/models` im Image | Allgemeine Vosk-/Piper-Modelle und Download-Manifest. | Bestandteil des Images; enthält keine persönlichen Trainingsdaten aus den Anrufen. |

Die Datenbank wird auch bei einem reinen Registrierungsstart angelegt, aber nur
zugelassene Rückrufreservierungen erzeugen Versuchseinträge. Abgewiesene
unbekannte Anrufer und direkte Gespräche werden darin nicht als Anrufhistorie
gespeichert. Fehlgeschlagene Rückrufe bleiben gezählte Versuche.

Das benannte Datenvolume bleibt bei gewöhnlichem Container-Neustart oder
Neuerstellen erhalten. Das Löschen des Containers allein entfernt daher weder
Ansagen noch Rückrufdaten. Ein Löschen der Datenbank setzt außerdem den
Rückrufschutz zurück. Backups oder extern gesammelte Logs haben eigene
Aufbewahrungsregeln.

## Docker-Logrotation und Einsicht

Die Compose-Vorlage setzt `max-size: 10m` und `max-file: "3"`. Mit dem im lokalen
Test tatsächlich verwendeten Treiber `json-file` entspricht das ungefähr drei
Logdateien zu je 10 MB pro Container. Es ist keine Frist von drei Tagen: Bei
wenigen Ereignissen können Daten wesentlich länger liegen bleiben. Die Vorlage
legt den Treiber nicht ausdrücklich fest; bei anderen Docker-Treibern deren
Unterstützung der Optionen prüfen.

Für die Compose-Installation, jeweils lesend:

```bash
docker compose logs --tail 100 controller
docker compose logs --since 1h controller
docker compose logs -f controller
docker compose exec controller cat /data/health.json
```

Im lokalen Testaufbau heißt der einzeln gestartete Container
`sip-voice-home-control-test`:

```bash
docker logs --tail 100 sip-voice-home-control-test
docker logs --since 1h sip-voice-home-control-test
docker exec sip-voice-home-control-test cat /data/health.json
```

`ok` bedeutet, dass die konfigurierte neue Geräterückmeldung eingetroffen ist.
`failed` bedeutet einen beobachteten Fehler bzw. eine klare Ablehnung.
`unconfirmed` bedeutet, dass keine hinreichende Bestätigung vorliegt; der Befehl
kann trotzdem bereits angekommen sein. Aus `unconfirmed` keine automatische
Wiederholung ableiten. `disabled` kennzeichnet eine nicht aktivierte Aktion.

CLI-Befehle wie `validate`, `parse`, `doctor` und `register` geben ihre Ergebnisse
zusätzlich auf stdout aus. Bei `parse` steht der übergebene Testtext auch in der
Befehlszeile und gegebenenfalls in der Shell-Historie. Der synthetische
Prüflauf `scripts/verify_speech.py` protokolliert seine vorgegebenen Testsätze und
Erkennungsergebnisse; er verwendet keine Telefonaufnahmen.

## Zeitweilige Diagnose im lokalen Testaufbau

Bei der Fehlersuche wurde separat ein lokaler Diagnose-Wrapper unter `.build/`
verwendet. Das ist kein regulärer YAML-Schalter und kein Bestandteil des
ausgelieferten Container-Images.

Die Textdiagnose konnte für zehn Minuten erkannte Wörter, Konfidenzen,
Wortzeitpunkte, Dialogentscheidungen und Ansagetexte protokollieren. In einem
angekündigten Test wurden außerdem zwei kurze eingehende Tonproben lokal
gespeichert und ohne Cloud-Upload ausgewertet. Diese WAV-Tonproben wurden
anschließend gelöscht.

Stand der lokalen Kontrolle am 30.09.2026:

- Der laufende Container startet normal mit `voice-home serve`, ohne Diagnose-Wrapper.
- Im lokalen Ordner `.build/audio-diagnostics/` liegen keine WAV-Tonproben mehr.
- Exportierte Diagnose-Textlogs unter `.build/` sowie zwei JSON-Metadatendateien
  mit Erkennungstext und Audiokennwerten sind weiterhin vorhanden. Sie werden
  nicht von der Docker-Logrotation oder dem Zehn-Minuten-Zeitlimit gelöscht.
- Die Diagnoseprotokolle können Sprachtexte, Aktionsentscheidungen, Adressen
  und Item-Namen enthalten. Das Abschalten der Diagnose löscht diese alten
  Dateien nicht rückwirkend.

Diese lokalen Diagnoseartefakte, persönlichen Konfigurationen, Secret-Dateien,
WAVs, Logs und SQLite-Dateien sind durch die Projektregeln von Git bzw. dem
Docker-Build-Kontext ausgeschlossen. Das ist keine Zugriffssperre auf dem Host
und keine Lösch- oder Backupregel. Vor dem Teilen nur geprüfte Auszüge verwenden.

## Netzwerk und Grenzen

Die Anwendung verwendet für Sprachverarbeitung keine Cloud-Dienste. Im Betrieb
kommuniziert sie mit der FRITZ!Box über SIP/RTP und mit openHAB über HTTP(S)/SSE.
Modell- und Paketdownloads erfolgen beim Image-Build. Die ONNX-Telemetrie wird
im Sprachmodul ausdrücklich abgeschaltet.

Die Protokolle und Anruflisten von FRITZ!Box, Telefonanbieter, openHAB sowie
gegebenenfalls Reverse-Proxy, Docker-Host und Backups sind davon unabhängig.
Diese Anwendung verwaltet oder löscht deren Daten nicht.

Aktuell gibt es keine YAML-Schalter für Log-Level, automatische
Transkriptaufzeichnung, Gesprächsaufnahmen, Ansagen-Aufbewahrungsdauer oder
regelmäßige Löschung aller personenbezogenen Daten. Die Dokumentation beschreibt
den vorhandenen Stand; sie behauptet keine darüber hinausgehende Löschautomatik.
