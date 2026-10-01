# Controller in openHAB bedienen

## Einrichtung

Die vier Items aus `examples/controller.items` in das aktive openHAB-Verzeichnis
`conf/items/voice_controller.items` kopieren. Die Regel aus
`examples/controller.rules` unter `conf/rules/voice_controller.rules` ablegen.
Keine gleichnamigen Items zusätzlich über MainUI anlegen. Dateibasierte Items
werden über die `.items`-Datei bearbeitet.

In der Controller-YAML aktivieren:

```yaml
call_control:
  enabled: true
  initial_accepting: false
  switch_item: VoiceController_AcceptCalls
  status_item: VoiceController_Status
  call_active_item: VoiceController_CallActive
  heartbeat_item: VoiceController_Heartbeat
  heartbeat_interval_seconds: 10
```

Nach Anpassungen im LXC:

```bash
cd /opt/sip-voice-home
./voice-home-deploy.sh check
./voice-home-deploy.sh apply
```

Vor `apply` oder `update` Annahme ausschalten und das Ende laufender Gespräche
abwarten. Das Skript verweigert einen Austausch bei aktiver Annahme oder Belegung.

## Bedienung ohne eigene Steuerregeln

In openHAB MainUI unter Einstellungen → Items nach `VoiceController_` suchen.
Für eine eigene Bedienseite einen Switch für `VoiceController_AcceptCalls` und
Anzeigen für Status, Gespräch und Lebenszeichen verwenden. Status und Gespräch
sind Rückmeldungen und sollten nur angezeigt werden.

- Annahme ON: neue Anrufe zugelassen; bei Leerlauf Status `READY`.
- Annahme OFF: neue Anrufe abweisen, wartende Rückrufe verwerfen. Bereits
  gestartete Rückrufe und Gespräche dürfen fertiglaufen; dann `DISABLED`.
- `CallActive=ON`: eine bestätigte SIP-Verbindung besteht. Ein nur klingelnder
  Rückruf ist bereits `BUSY`, aber noch kein aktives Gespräch.
- Statuspriorität: OFFLINE, STARTING, ERROR, BUSY, DISABLED, READY.

Der Controller empfängt ON/OFF-Kommandos per SSE über `/rest/events`. Er schreibt
bestätigte Zustände per REST zurück. `autoupdate="false"` verhindert eine bloß
vorhergesagte Schalterstellung. Für Regeln `sendCommand(ON/OFF)` verwenden;
`postUpdate` schaltet den Controller nicht.

Die Rückmeldungen werden bei Änderungen und spätestens mit dem Lebenszeichen
alle zehn Sekunden veröffentlicht. Kein Webhook oder HTTP-Port am Controller
ist erforderlich. Er benötigt Zugriff auf openHAB-REST und den Ereignisstrom.
Falls eine Authentifizierung verlangt wird, `openhab.token_file` oder `token`
konfigurieren; keine Zugangsdaten in die Itemdateien schreiben.

## Ausfall und Neustart

Das Heartbeat-Item hat `expire="30s,state=UNDEF"`. Bleibt es aus, setzt die kleine
Regel den Status auf `OFFLINE` und beide Switches auf `UNDEF`. UNDEF bedeutet
unbekannt, nicht ausgeschaltet. Bei einem vollständigen openHAB-Ausfall kann
openHAB selbst keine Ausfallregel ausführen.

Nach Wiederverbindung veröffentlicht der Controller seine tatsächlichen Werte.
Gespeicherte Itemzustände werden nicht als neue Befehle übernommen; während
einer Trennung gesendete Befehle müssen wiederholt werden. Der Controller behält
während einer openHAB-Störung seine bisherige Annahmefreigabe.

Nach Controller-Neustart gilt `initial_accepting`. Im obigen Beispiel ist dieser Wert false:
Nach einem Neustart bewusst wieder ON senden, wenn Anrufe angenommen werden sollen.

## Benachrichtigungen

Optionale Push-Meldungen mit Namen und bestätigter Aktion:
[Einrichtung und Regelbeispiele](OPENHAB_NOTIFICATIONS.md).
