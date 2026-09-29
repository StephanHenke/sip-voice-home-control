# Gesprächsablauf und sämtliche Ansagen

Stand des implementierten Dialogs. Texte in Anführungszeichen sind TTS-Ansagen.
`{Name}` stammt aus `callers[].name`, `{confirmation_text}` und `{success_text}`
aus der jeweiligen Aktion in der YAML. Die Bestätigungsfrage ist pro Aktion
optional und standardmäßig ausgeschaltet.
Ergebnistext und „Möchtest du noch etwas?“ werden zusammenhängend gesprochen.

```mermaid
flowchart TD
    Start([Anruf]) --> Allowed{Quelle und Nummer erlaubt?}
    Allowed -- Nein --> Silent([Beenden ohne Ansage])
    Allowed -- Ja --> Free{Gesprächsplatz frei?}
    Free -- Nein --> Silent
    Free -- Ja --> Mode{Zugangsmodus}
    Mode -- direct --> Answer[Annehmen]
    Mode -- callback --> Limit{Rückruflimit eingehalten?}
    Limit -- Nein --> Silent
    Limit -- Ja --> Trigger[Abweisen oder kurz annehmen und auflegen<br/>ohne Ansage]
    Trigger --> Callback[Rückrufpause, dann gespeicherte Nummer wählen]
    Callback --> Connected{Rückruf angenommen?}
    Connected -- Nein / Fehler / Zeitlimit --> Silent
    Connected -- Ja --> Media
    Answer --> Media{Audio verfügbar?}
    Media -- Nach 10 s weiterhin nein --> Silent
    Media -- Ja --> Delay[Konfigurierte Begrüßungspause]
    Delay --> Active{Aktivierte Aktionen vorhanden?}
    Active -- Ja --> Greeting["Hallo {Name}, was möchtest du tun?"]
    Active -- Nein --> Empty["Hallo {Name}, was möchtest du tun?<br/>Aktuell ist noch keine Aktion eingerichtet."]
    Greeting --> Beep[Signalton, dann zuhören]
    Empty --> Beep
    Beep --> Input{Eingabe}
    Input -- Geräusch ohne erkannten Text --> Wait[Im ursprünglichen Antwortfenster weiter zuhören<br/>kein neuer Signalton, kein Fehlversuch]
    Wait --> Input
    Input -- Nein / Auflegen / Abbrechen --> Bye["Auf Wiederhören."]
    Bye --> End([Auflegen])
    Input -- Ja als Antwort auf Folgefrage --> Ask["Was möchtest du tun?"]
    Ask --> Beep
    Input -- Unklar / geringe Sicherheit / Schweigen --> Failures{Fehlergrenze erreicht?}
    Failures -- Nein --> Retry["Bitte nenne eine Aktion,<br/>zum Beispiel Haustür öffnen."]
    Retry --> Beep
    Failures -- Ja --> GiveUp["Ich konnte dich nicht verstehen.<br/>Auf Wiederhören."]
    GiveUp --> End
    Input -- Aktion erkannt --> Enabled{Aktion aktiviert?}
    Enabled -- Nein --> Disabled["Diese Aktion ist noch nicht eingerichtet."]
    Enabled -- Ja --> ConfirmRequired{Bestätigungsfrage für diese Aktion?}
    ConfirmRequired -- Nein --> Execute[Befehl einmal senden<br/>und neues Gerätefeedback prüfen]
    ConfirmRequired -- Ja --> Confirm["{confirmation_text}<br/>z. B. Soll ich das Garagentor öffnen?"]
    Confirm --> ConfirmBeep[Signalton, dann Bestätigung anhören]
    ConfirmBeep --> Confirmation{Antwort}
    Confirmation -- Geräusch ohne erkannten Text --> ConfirmWait[Im ursprünglichen Antwortfenster weiter zuhören]
    ConfirmWait --> Confirmation
    Confirmation -- Ja / Ja bitte --> Execute
    Confirmation -- Nein / Abbrechen --> Cancelled["Abgebrochen."]
    Confirmation -- Auflegen / Tschüss --> Bye
    Confirmation -- Unklar / unsicher / Schweigen / anderer Auftrag --> ConfirmFailures{Fehlergrenze erreicht?}
    ConfirmFailures -- Ja --> GiveUp
    ConfirmFailures -- Nein --> ConfirmRetry["Bitte antworte mit Ja oder Nein.<br/>{confirmation_text}"]
    ConfirmRetry --> ConfirmBeep
    Execute --> Result{Ergebnis}
    Result -- Erfolg bestätigt --> Success["{success_text}<br/>z. B. OK, das Garagentor öffnet sich.<br/>OK, das Garagentor ist geschlossen.<br/>oder OK, die Haustür ist freigegeben."]
    Result -- Fehler festgestellt --> Failed["Fehlgeschlagen."]
    Result -- Unklar / keine neue Bestätigung --> Unconfirmed["Die Ausführung konnte<br/>nicht bestätigt werden."]
    Result -- Aktion deaktiviert --> Disabled
    Success --> Follow["Möchtest du noch etwas?"]
    Failed --> Follow
    Unconfirmed --> Follow
    Disabled --> Follow
    Cancelled --> Follow
    Follow --> Beep
    Abort[Anrufer legt auf / Verbindung bricht ab<br/>oder maximale Gesprächsdauer erreicht] --> Silent
```

Der Abbruchpfad gilt jederzeit, auch während einer Ansage oder Geräteaktion.
Beim Höchstzeitlimit gibt es derzeit keine zusätzliche Abschiedsansage. Fehlendes
Audio und technische Wiedergabefehler können ebenfalls ohne Ansage beenden.
Ein bereits gesendeter Gerätebefehl lässt sich durch Auflegen nicht zurücknehmen.

Nach einer Folgefrage kann direkt die nächste Aktion genannt werden; „Ja“ ist
nicht erforderlich. Dieselbe Aktion darf mehrfach angefordert werden und muss
bei eingeschalteter Bestätigungsfrage jedes Mal neu bestätigt werden. „Ja“ auf
die Folgefrage fordert einen neuen Auftrag an; es wiederholt keine alte Aktion.
Ohne Folge- oder Bestätigungsfrage wird „Ja“ als unklare Eingabe behandelt.

Bei einer Bestätigungsfrage brechen „Nein“, „Nein danke“, „Nee danke“, „Nö“ und
„Abbrechen“ nur die angefragte Aktion ab. Außerhalb dieser Bestätigungsfrage
beenden diese Wörter den Dialog. „Auflegen“ und „Tschüss“ beenden immer den Dialog
bei ausreichend sicherer Erkennung. Ein anderer Auftrag während der
Bestätigungsfrage wird nicht ausgeführt; die Frage zur ursprünglichen Aktion
wird erneut gestellt.

Standardwerte: 1 s Begrüßungspause, 3 s Rückrufpause, 15 s bis zum Antwortbeginn,
15 s ab erkanntem Sprechbeginn, 2 aufeinander folgende Verständnisfehler und
120 s maximale Gesprächsdauer. Spracherkennung und Echo-Schutzpause werden vor
dem Signalton vorbereitet; unmittelbar nach dem Ton beginnen Aufnahme und
Antwortfrist. Nach normalen Ansagen
kommt ein kurzer Signalton; nach einer Abschiedsansage wird direkt aufgelegt.
Während Ansagen und Befehlsausführung werden keine Sprachbefehle ausgewertet.

Ein kurzer Ton-/Geräuschimpuls ohne erkannten Text wird ignoriert. Dabei bleibt
das ursprüngliche Antwortfenster erhalten, auch bei einer Bestätigungsfrage.
Eine erkannte begonnene Äußerung bekommt ihre eigene, begrenzte Sprechfrist.

Die Nachfrage nennt aktuell fest „Haustür öffnen“, auch wenn nur andere Aktionen
aktiviert sind. Namen, Bestätigungsfragen und Erfolgsansagen sind variabel; die
übrigen hier gezeigten Ansagetexte stehen derzeit in `src/voice_home/dialog.py`.
Zusätzliche YAML-Aktionen bringen ihre eigene Erfolgsansage mit.
