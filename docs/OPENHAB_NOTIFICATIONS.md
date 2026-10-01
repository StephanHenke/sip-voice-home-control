# Push-Benachrichtigungen mit openHAB

Der Controller veröffentlicht nur nach bestätigtem Aktionserfolg einen Text mit
konfiguriertem Namen. Telefonnummern und Sprachtranskripte werden nicht übertragen.
Die Übertragung nutzt denselben Smart-Home-Adapter wie Geräte- und Statuszugriffe.

## Einrichten

1. openHAB Cloud Connector mit myopenHAB verbinden und die Mobilgeräte in der
   openHAB-App beim zugehörigen Konto anmelden; Benachrichtigungen erlauben.
2. `examples/notifications.items` nach `conf/items/voice_controller_notifications.items`
   kopieren und `examples/notifications.rules` nach
   `conf/rules/voice_controller_notifications.rules`.
3. Controller-YAML ergänzen und nach Validierung neu laden:

```yaml
smarthome:
  adapter: openhab
  notification_item: VoiceController_Notification

# In den bereits vorhandenen Aktionen ergänzen:
actions:
  - id: front_door_open
    # übrige Felder der Aktion beibehalten
    notification_text: "{name} hat die Haustür aufgeschlossen."
  - id: garage_open
    # übrige Felder der Aktion beibehalten
    notification_text: "{name} öffnet das Garagentor."
```

Dies ist ein Ausschnitt, keine vollständige Ersatzkonfiguration. `notification_item`
ist optional (Standard leer = aus); es muss ein eigenes String-Item sein. Pro Aktion
aktiviert ein nichtleerer `notification_text` die Meldung (Standard leer = aus).
Der einzige Platzhalter ist `{name}`; maximal 500 Zeichen, keine Zeilenumbrüche.
Das Namensfeld kommt aus der konfigurierten Rufnummernzuordnung, nicht aus SIP-
Anzeigenamen oder erkannten Worten. Namen können in der YAML angepasst werden.

Bei der aktuellen Haustüraktion bedeutet Erfolg Entriegeln und Falle ziehen.
Die Garage bestätigt bereits den Zustand „opening“; deshalb lautet der Text
„öffnet“ und behauptet nicht, dass das Tor vollständig offen ist. Für „hat das
Garagentor geöffnet“ muss die Aktion tatsächlich nur `open` als Erfolg werten
und ausreichend lange auf diese Rückmeldung warten.

## Beispiele für Regeln

Alle angemeldeten Geräte (so eingerichtet):

```java
rule "Voice controller confirmed action notification"
when
    Item VoiceController_Notification received command
then
    if (receivedCommand == NULL || receivedCommand == UNDEF) return;
    val message = receivedCommand.toString
    if (message.trim.length == 0) return;
    sendBroadcastNotification(message)
end
```

Nur einen bestimmten myopenHAB-Benutzer benachrichtigen: In derselben Regel die
letzte Zeile ersetzen (keine zweite Regel zusätzlich aktivieren):

```java
sendNotification("benutzer@example.org", message)
```

Separates Beispiel für Controller-Ausfall (optional, nicht automatisch installiert):

```java
rule "Voice controller offline push"
when
    Item VoiceController_Status changed to "OFFLINE"
then
    sendBroadcastNotification("Der Sprachcontroller ist nicht erreichbar.")
end
```

Die Aktionsregel verwendet `received command`, damit auch zwei gleiche, erfolgreich
bestätigte Aktionen nacheinander zwei Meldungen erzeugen. Sie verwendet `receivedCommand`
für genau dieses Ereignis; sie liest keinen später möglicherweise geänderten Namen.
Das dedizierte Ereignis-Item hat `autoupdate="false"`; der Controller sendet einen
String-Befehl statt eines gespeicherten Zustands. Deshalb lösen wiederhergestellte
Itemzustände nach einem Neustart keine Push-Meldungen aus. Keine Gerätekanäle oder
anderen Steuerregeln mit diesem Item verknüpfen.

## Zustellung, Daten und Tests

Keine Meldung bei nicht verstandenem Befehl, abgelehnter Bestätigung, deaktivierter
Aktion, Fehler oder unbestätigter Ausführung. Die Push-Zustellung beeinflusst weder
Gerätebefehl noch Sprachantwort. Die RAM-Warteschlange ist auf 32 Meldungen begrenzt;
Einträge älter als 30 Sekunden werden verworfen. Bei Überlauf/Netzwerkfehler gibt es
nur einen wertfreien Warnhinweis, keinen Versandretry und keine Speicherung auf
Platte. Neustarts verlieren wartende Meldungen. Push ist best effort: Eine erfolgreiche
REST-Übergabe beweist nicht, dass ein Mobilgerät die Meldung bereits angezeigt hat.

Das Ereignis enthält den Nachrichtentext inklusive Name. openHAB kann diesen
in Ereignislogs speichern; durch `autoupdate="false"` bleibt der Itemzustand unverändert. Die Cloud und die Push-Dienste der
Mobilplattform erhalten den Nachrichtentext; dies gilt unabhängig davon, dass die
Spracherkennung lokal erfolgt. Keine Namen oder Nachrichtentexte in Controllerlogs.

Für einen Test ohne Tür-/Torbetätigung kann ausschließlich das Benachrichtigungs-
Item mit einem klar markierten String-Befehl angesprochen werden, beispielsweise:
`TEST: Sprachcontroller-Push eingerichtet – keine Tür oder Garage betätigt.`
Eine echte Erfolgsmeldung erst mit einem vom Benutzer ausgelösten Anruf prüfen.

Offizielle Dokumentation: [openHAB Cloud Connector](https://www.openhab.org/addons/integrations/openhabcloud/).
