# Geräte über YAML konfigurieren

Alle Item-Namen und Befehle stehen pro Aktion unter `actions` in `config.yaml`
(im lokalen Testaufbau `config.local.yaml`). Im Python-Code sind keine privaten
Item-Namen hinterlegt. `command_item` empfängt den Befehl, `feedback_item` liefert
die tatsächliche Rückmeldung. Beide dürfen dasselbe Item benennen.

Nach Änderungen zuerst `validate` ausführen und den Controller neu starten.
Ein Image-Neubau ist für reine YAML-Änderungen nicht nötig. `doctor` liest die
konfigurierten Items; weder `validate` noch `doctor` sendet Gerätebefehle.

## Diskrete Statuswerte: offen, geschlossen und Bewegung

Vollständiges Beispiel mit Platzhalter-Items und beispielhafter Gerätecodierung:

```yaml
actions:
  - id: garage_open
    enabled: false  # Nach Anpassung und beaufsichtigtem Test aktivieren
    aliases: [Garagentor, Garage]
    patterns: ["{target} öffnen", "öffne das {target}", "öffne die {target}"]
    command_item: GarageDoor_Command
    command: "UP"
    feedback_item: GarageDoor_Status
    feedback_mode: state
    state_values:
      closed: ["1"]
      opening: ["3"]
      open: ["2"]
      error: ["9"]
    success_states: [opening, open]
    failure_states: [error]
    timeout_seconds: 10
    success_text: "OK, das Garagentor öffnet sich."
```

Die Rohwerte sind gerätespezifisch, keine openHAB-Standardcodierung. Zahlen in
Anführungszeichen schreiben. Statusnamen sind frei wählbar, beispielsweise auch
`locked`, `unlatched`, `on` oder `off`. Jeder Rohwert darf nur einem Status
zugeordnet sein. Erfolgs- und Fehlerzustände müssen definiert und verschieden sein.
`NULL` und `UNDEF` dürfen nie als Erfolg dienen.

Mit `success_states: [open]` wird erst die vollständige Öffnung bestätigt. Dazu
`timeout_seconds` passend zur Fahrzeit wählen (höchstens 60 Sekunden) und zum
Beispiel `success_text: "OK, das Garagentor ist offen."` setzen. Ein reiner Kontakt
weist nur seinen Schaltzustand nach; „öffnet sich“ nur mit einer passenden
Geräterückmeldung verwenden.

Ein Rohwertwechsel zwischen zwei Werten desselben benannten Zustands gilt nicht
als neuer Erfolg. War das Tor bereits offen, ergibt ein erneut gemeldetes „offen“
keine neue Erfolgsbestätigung.

## Kontaktstatus umkehren

Für einen Kontakt, der bei tatsächlich offener Tür `CLOSED` liefert, wird die
Zuordnung ausdrücklich umgekehrt. Diese Felder ersetzen die obige Zuordnung:

```yaml
feedback_mode: state
state_values:
  open: ["CLOSED"]
  closed: ["OPEN"]
success_states: [open]
failure_states: []
success_text: "OK, die Tür ist offen."
```

Eine zusätzliche globale Invertierung ist dafür nicht nötig. So bleibt auch eine
Codierung mit mehr als zwei Werten eindeutig. Vorhandene Konfigurationen mit
`success_values` und `failure_values` werden weiterhin unterstützt. Bei Verwendung
von `state_values` diese direkten Wertelisten entfernen oder leer lassen.

## Rollershutter-Prozentwerte und ein gemeinsames Item

In einer vorhandenen Aktion diese Felder verwenden:

```yaml
command_item: GarageDoor
command: "UP"
feedback_item: GarageDoor
feedback_mode: rollershutter_opening
open_position: 0
closed_position: 100
state_values: {}
success_states: []
failure_states: []
success_values: []
failure_values: []
success_text: "OK, das Garagentor öffnet sich."
```

Invertiert werden nur die Endpositionen vertauscht:

```yaml
open_position: 100
closed_position: 0
```

Eine neue gemessene Position näher am konfigurierten offenen Ende bestätigt die
Bewegung. Gleichbleibende Werte, Bewegung in die Gegenrichtung, `NaN`, `NULL`,
`UNDEF` und Werte außerhalb der eingestellten Endpositionen bestätigen nichts.
Die Endpositionen müssen verschieden sein und zwischen 0 und 100 liegen.
`command` bleibt unabhängig davon der tatsächlich benötigte Öffnungsbefehl:
`UP`, `DOWN` oder eine als String angegebene Zielposition zwischen 0 und 100.
Die Positionsauswertung und eine diskrete Zustandszuordnung sind alternative Modi.

**Bei einem einzigen Item gilt in beiden Modi:** In openHAB muss dessen
autoupdate-Metadatum ausdrücklich `false` sein, und das Binding bzw. eine Regel
muss echte Geräteupdates liefern. Beispiel in einer `.items`-Datei:

```java
Rollershutter GarageDoor "Garagentor" { autoupdate="false" }
```

Die bestehende Channel-Verknüpfung bzw. Geräteregel bleibt erforderlich; die Zeile
oben zeigt nur das Metadatum. Der Controller ändert es nicht automatisch. Ohne
`autoupdate=false` wird der Befehl einmal gesendet, aber kein OK aus dessen
vorhergesagtem Zustand abgeleitet. Eine Regel, die den Befehl nur spiegelt, ist
auch bei deaktiviertem autoupdate kein belastbares Gerätefeedback.

## Haustür: entriegeln und Falle ziehen

Bei getrennten Aktions- und Statuskanälen unterschiedliche Items verwenden.
Diese Beispielwerte passen zu einer Integration mit `3 = Falle öffnen` und
`5 = Falle geöffnet`; vor Verwendung mit der eigenen Integration abgleichen:

```yaml
command_item: FrontDoor_Action
command: "3"
feedback_item: FrontDoor_State
feedback_mode: state
state_values:
  locked: ["1"]
  unlocking: ["2"]
  unlocked: ["3"]
  unlatched: ["5"]
  blocked: ["254"]
success_states: [unlatched]
failure_states: [blocked]
timeout_seconds: 10
success_text: "OK, die Haustür ist freigegeben."
```

„Entriegelt“ alleine bestätigt hier nicht das Ziehen der Falle. Der Zustand
`unlatched` beschreibt die Schlossfreigabe, nicht den physischen Türkontakt.
Andere Geräte können andere Codes verwenden. Die Steuerung sendet keine
automatischen Wiederholungen und führt dieselbe Aktion höchstens einmal pro
Gespräch aus.
