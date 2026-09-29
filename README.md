# SIP Voice Home Control

Lokale Sprachsteuerung für openHAB über Telefonanrufe an eine FRITZ!Box.
Ein Linux-Docker-Container, CPU-Verarbeitung, kein LLM, keine Cloud-Sprachdienste.
Ausgelegt für kurze deutsche Befehle, beispielsweise von einer Xplora-Uhr.

**Status:** Erste Implementierung. Automatisierte Kerntests sind vorhanden.
Die reale SIP-/RTP-Verbindung, Verständlichkeit an der Uhr und physische
Geräterückmeldungen müssen vor dem produktiven Einsatz abgenommen werden.
Alle Aktionen und Anruferfreigaben sind in der Beispielkonfiguration deaktiviert.
Bereits durchgeführte Prüfungen stehen in [VALIDATION.md](docs/VALIDATION.md).

## Funktionen

- Registrierung als SIP-Telefon an der FRITZ!Box, Audio über G.722/G.711.
- Rufnummer und Begrüßungsname werden gemeinsam konfiguriert.
- Pro Rufnummer Rückrufschutz (`callback`, Standard) oder direkte Annahme (`direct`).
- Rückruf ausschließlich an die hinterlegte Nummer; dauerhafte Begrenzung der Versuche.
- Einstellbare Pause nach Gesprächsannahme, standardmäßig eine Sekunde.
- „Öffne die Haustür“, „Tür öffnen“, „schließe die Tür auf“, „Tür aufschließen“
  und weitere konfigurierte Satzmuster führen zur gleichen Aktion.
- Bestätigung erst nach einer neuen, separaten openHAB-Geräterückmeldung.
- Mehrere unterschiedliche Aktionen je Gespräch; „Nein“ beendet den Dialog.
- Erweiterung um Lichtaktionen über Konfiguration, ohne ein Sprachmodell umzuprogrammieren.

## Schnellstart auf Linux (amd64)

Voraussetzungen: Docker Engine mit Compose, Verbindung zur FRITZ!Box und zu openHAB.
Als Ausgangspunkt zwei CPU-Kerne und 2 GB RAM einplanen; reale Last und Latenz messen.

```bash
git clone https://github.com/OWNER/sip-voice-home-control.git
cd sip-voice-home-control
cp config.example.yaml config.yaml
mkdir -m 700 secrets
install -m 600 /dev/null secrets/sip_password
install -m 600 /dev/null secrets/openhab_token
# Secret-Dateien mit einem Editor befüllen; Passwörter nicht in Befehlszeilen schreiben.
# config.yaml bearbeiten: SIP, openHAB und freigegebene Anrufer eintragen.
# Der Container läuft mit UID 10001; Secret-Dateien müssen für diese UID lesbar sein.
sudo chown 10001:10001 secrets/sip_password secrets/openhab_token
docker compose build
docker compose run --rm controller validate
docker compose run --rm controller doctor
docker compose run --rm controller register --seconds 15
docker compose up -d
docker compose logs -f
```

`register` testet ausschließlich die Anmeldung und weist alle Anrufe ab. Es führt
keine Rückrufe oder Gerätebefehle aus. Diesen Test nicht parallel zu `serve`
mit demselben SIP-Konto/Port betreiben.

Das Image enthält PJSIP, Vosk und Piper samt deutschen Modellen. Downloads erfolgen
beim Build. Beim ersten Start werden die persönlichen Ansagen erzeugt. Danach
benötigt die Sprachverarbeitung keinen Internetzugriff.

**Dateien mit persönlichen Daten:** `config.yaml`, `config.local.yaml`, `secrets/`
und `data/` sind in Git und im Docker-Build-Kontext ausgeschlossen. Passwörter,
echte Rufnummern und private Item-Namen gehören nicht in Beispiele oder Issues.

## FRITZ!Box und Uhr

1. Unter Telefonie → Telefoniegeräte ein LAN/WLAN-IP-Telefon anlegen.
2. Dem Gerät eine eigene eingehende und ausgehende Rufnummer zuweisen.
3. Registrar-IP, SIP-Benutzername und Passwort lokal konfigurieren.
4. Die externe Controller-Rufnummer als erlaubten Kontakt in der Uhr hinterlegen.
5. Die Rufnummer der Uhr mit Namen unter `callers` eintragen. Sie ist im Rückrufmodus
   zugleich das feste Rückrufziel. Die Controller-Rufnummer ist kein erlaubter Anrufer.

Auf Linux verwendet Compose Host-Netzwerk. Standardports: SIP UDP 5062 am Controller,
SIP UDP 5060 an der FRITZ!Box und RTP/RTCP UDP 40000–40010 am Controller.
Bei getrennten VLANs müssen diese Wege einschließlich der tatsächlich von der
FRITZ!Box verwendeten Medienadresse erreichbar sein. Keine Internet-Portfreigabe
für den Controller einrichten. SIP-Anrufe werden nur von `sip.host` akzeptiert.
`sip.public_address` kann die im SIP/SDP angekündigte erreichbare Host-IP festlegen.

Die Compose-Datei ist für natives Linux vorgesehen. Docker Desktop kann für einen
Build verwendet werden; seine Netzwerkeinstellungen erfordern für reale Anrufe
eine eigene Prüfung.

`sip.transport: tcp` verwendet TCP für Registrierung und Rückruf-Signalisierung;
Audio bleibt RTP/UDP. Bei Docker Desktop den SIP-Port entsprechend als TCP sowie
die RTP-Ports als UDP veröffentlichen. Docker Desktop ersetzt bei UDP unter Umständen
die Quell-IP durch seine Gateway-Adresse, wodurch die FRITZ!Box-Prüfung den Anruf
abweist. Im getesteten Aufbau bleibt über die TCP-Verbindung die FRITZ!Box-Adresse
erhalten. Die Absenderprüfung bleibt für beide Transportarten aktiv.

## Anrufer und Rückruf

```yaml
callers:
  - number: "+49..."  # vollständig ersetzen
    name: "Anna"
    access_mode: callback
dialog:
  answer_delay_ms: 1000
callback:
  trigger_mode: reject
  delay_ms: 3000
  ring_timeout_seconds: 30
  cooldown_seconds: 60
  max_attempts_per_number_per_hour: 5
```

Im Rückrufmodus wird der eingehende Anruf ohne Audio mit SIP 603 „Decline“ abgewiesen.
Anders als „Busy Here“ (486) signalisiert dies eine globale Ablehnung, damit die
Telefonanlage weitere parallele Rufzweige beendet. Die konkrete Behandlung durch
die FRITZ!Box muss beim Testanruf geprüft werden.
Wenn die Telefonanlage trotzdem weiterklingelt, kann `callback.trigger_mode:
answer_hangup` gewählt werden. Der Controller nimmt dann ohne Ansage an und legt
nach bestätigtem Verbindungsaufbau sofort auf. Dabei wird kein Sprachdialog
gestartet und kein Audio an die Spracherkennung angeschlossen. Erst nach dem
Auflegen und der Rückrufpause wird die gespeicherte Nummer gewählt. Schlägt die
Annahme fehl, erfolgt kein Rückruf. Das kurze Annehmen kann tarifabhängig als
angenommener Anruf berechnet werden.
Nach dessen Ende und der Rückrufpause wird die konfigurierte Nummer gewählt.
Erst nach Annahme und Bereitstellung des Audiokanals beginnt die Begrüßungspause. `answer_delay_ms: 0` deaktiviert
diese zusätzliche Pause. Folgeansagen warten nicht erneut.

Fehlschläge zählen zum Rückruflimit. Es gibt keine Wahlwiederholung, keinen
Fallback auf direkte Annahme und keine Rückrufwarteschlange. Ein aktiver oder
ausstehender Rückruf belegt den einzigen Gesprächsplatz. SIP-Weiterleitungen
und Transfers werden abgelehnt. Eine gefälschte Caller-ID kann damit einen
begrenzten Rückruf auslösen, aber keinen Dialog auf der eingehenden Verbindung
erhalten. Rufumleitungen im Telefonnetz oder Zugriff auf den hinterlegten Anschluss
liegen außerhalb dieses Schutzes; dies ist keine persönliche Identitätsprüfung.

## Aktionen und Sprache

Die vollständige Konfiguration steht in [config.example.yaml](config.example.yaml).
Jede Aktion hat eine eindeutige `id`, Ziel-Aliase und Satzmuster mit `{target}`.
„Bitte“ wird automatisch an den Wortgrenzen zugelassen. Andere Wörter werden nicht
einfach entfernt. Es gibt keinen unscharfen Teilstring-Abgleich.

Es wird das vollständige ASR-Ergebnis geprüft. Ein eingeschränktes Wörterbuch wird
bewusst nicht erzwungen, damit „nicht öffnen“ oder Fremdgespräche nicht automatisch
auf einen erlaubten Befehl projiziert werden. Niedrige Wortkonfidenz führt zur
Nachfrage. `min_confidence` ist ein Startwert und muss mit realen Stimmen geprüft werden.
Negationen, unbekannte Ziele und mehrere Aktionen in einem Satz führen zu keiner Aktion.

Beispiel einer später ergänzten Lichtaktion:

```yaml
- id: hallway_light_on
  enabled: false
  aliases: ["Flurlicht", "Licht im Flur"]
  patterns: ["{target} einschalten", "schalte das {target} ein"]
  command_item: HallwayLight_Command
  command: "ON"
  feedback_item: HallwayLight_ActualState
  success_values: ["ON"]
  failure_values: []
  timeout_seconds: 5
  success_text: "OK, das Flurlicht ist eingeschaltet."
```

Ein-/Ausschalten werden als getrennte Aktionen konfiguriert. Sprachmuster dürfen
nicht mehrere Aktionen gleichzeitig bezeichnen. Das wird beim Start geprüft.

## Rückmeldungen richtig anschließen

Ein HTTP-Status 200/202 bestätigt nur die Annahme eines Befehls. Der Controller
abonniert vor dem Versand den Ereignisstrom des separaten `feedback_item` und
wartet auf eine passende neue Rückmeldung. Ein bereits bestehender Erfolgszustand
wird nicht als neuer Erfolg ausgegeben. NULL/UNDEF werden nicht als Erfolg gewertet.

Das Rückmelde-Item muss tatsächlich vom Gerät stammen. Ein durch `autoupdate`
vorhergesagter Zustand oder eine Regel, die nur den Befehl spiegelt, genügt nicht.
Für die Haustür bestätigt „Falle geöffnet“ die Freigabe; die Person muss die Tür
nicht erst physisch aufdrücken. Für das Garagentor muss ein tatsächlicher Öffnungsbeginn
konfiguriert werden. Ein reiner Offen-/Geschlossen-Kontakt kann je nach Installation
diese Aussage nicht liefern.

Für ein Garagentor vom Typ `Rollershutter` unterstützt die Beispielkonfiguration
`command: UP` mit `feedback_mode: rollershutter_opening`. Eine neue, kleinere
Prozentposition bestätigt den Öffnungsbeginn (0 = offen, 100 = geschlossen).
Befehls- und Rückmelde-Item dürfen in diesem Modus identisch sein. In diesem Fall
muss das Item `autoupdate="false"` haben und seine Updates aus der realen
Geräterückmeldung beziehen. Ohne explizit ausgeschaltetes autoupdate wird UP zwar
gesendet, aber eine vorhergesagte Position niemals als Erfolg angesagt; das
Ergebnis lautet „Die Ausführung konnte nicht bestätigt werden“. Der Controller
ändert die openHAB-Item-Konfiguration nicht automatisch.

Nach einem Gerätefehler wird „Fehlgeschlagen“ angesagt, nach ausbleibender oder
unklarer Rückmeldung „Die Ausführung konnte nicht bestätigt werden“. Befehle werden
auch nach Netzwerkfehlern nicht automatisch wiederholt. Dieselbe Aktion wird pro
Gespräch höchstens einmal angefordert.

## Entwicklung und Abnahme

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
voice-home --config config.example.yaml validate
voice-home --config config.example.yaml parse 'schließe die Tür auf'
```

Die Tests ohne native Bibliotheken prüfen Parser, Konfiguration, Gesprächsablauf,
Rückruflimits und openHAB-Fehlerfälle. Der GitHub-Actions-Workflow enthält zusätzlich
einen Container-Build und einen Offline-Test mit echter TTS, ASR und PJSIP-Audio.
Dieser Test ist auch lokal ausführbar:

```bash
docker run --rm --network none --read-only --tmpfs /tmp:size=128m \
  --cpus 2 --memory 2g --entrypoint python sip-voice-home-control:local \
  /app/scripts/smoke_runtime.py
```

Vor Gerätefreigabe: [Abnahmecheckliste](docs/ACCEPTANCE.md) und
[vereinbarte Anforderungen](docs/REQUIREMENTS.md) durchgehen. Zielwerte sind
höchstens zwei Sekunden vom Sprechende zum Befehl und 500 ms von der Geräterückmeldung
zum Ansagebeginn in mindestens 95 % der realen Testfälle. Das sind Abnahmeziele,
keine bereits gemessenen Zusagen. Verbindungsaufbau und Anfangspausen werden separat gemessen.

Der Healthcheck prüft eine aktuelle Prozessmeldung, SIP-Registrierung und geladene
Sprachkomponenten. `doctor` prüft openHAB gesondert. Docker startet einen abgestürzten
Prozess neu; ein bloßer Status `unhealthy` löst durch Compose keinen Neustart aus.

## Komponenten und Lizenzen

Siehe [THIRD_PARTY.md](THIRD_PARTY.md). Das Repository ist zunächst privat.
Eine eigene Veröffentlichungslizenz ist noch nicht festgelegt.
