# Gesprächsablauf und sämtliche Ansagen

Stand des implementierten Dialogs. Texte in Anführungszeichen sind TTS-Ansagen.
`{Name}` stammt aus `callers[].name`, `{Ziele}` aus dem ersten Alias jeder
aktivierten Aktion, `{success_text}` aus der jeweiligen Aktion in der YAML.
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
    Active -- Ja --> Greeting["Hallo {Name}, was möchtest du tun?<br/>Verfügbar sind: {Ziele}."]
    Active -- Nein --> Empty["Hallo {Name}, was möchtest du tun?<br/>Aktuell ist noch keine Aktion eingerichtet."]
    Greeting --> Beep[Signalton, dann zuhören]
    Empty --> Beep
    Beep --> Input{Eingabe}
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
    Enabled -- Ja --> Used{Schon in diesem Gespräch angefordert?}
    Used -- Ja --> Duplicate["Diese Aktion wurde bereits angefordert."]
    Used -- Nein --> Execute[Befehl einmal senden<br/>und neues Gerätefeedback prüfen]
    Execute --> Result{Ergebnis}
    Result -- Erfolg bestätigt --> Success["{success_text}<br/>z. B. OK, das Garagentor öffnet sich.<br/>oder OK, die Haustür ist freigegeben."]
    Result -- Fehler festgestellt --> Failed["Fehlgeschlagen."]
    Result -- Unklar / keine neue Bestätigung --> Unconfirmed["Die Ausführung konnte<br/>nicht bestätigt werden."]
    Result -- Aktion deaktiviert --> Disabled
    Success --> Follow["Möchtest du noch etwas?"]
    Failed --> Follow
    Unconfirmed --> Follow
    Disabled --> Follow
    Duplicate --> Follow
    Follow --> Beep
    Abort[Anrufer legt auf / Verbindung bricht ab<br/>oder maximale Gesprächsdauer erreicht] --> Silent
```

Der Abbruchpfad gilt jederzeit, auch während einer Ansage oder Geräteaktion.
Beim Höchstzeitlimit gibt es derzeit keine zusätzliche Abschiedsansage. Fehlendes
Audio und technische Wiedergabefehler können ebenfalls ohne Ansage beenden.
Ein bereits gesendeter Gerätebefehl lässt sich durch Auflegen nicht zurücknehmen.

Nach einer Folgefrage kann direkt die nächste Aktion genannt werden; „Ja“ ist
nicht erforderlich. „Ja“ ohne vorangehende Folgefrage wird als unklare Eingabe
behandelt. „Nein“, „Nein danke“, „Nee danke“, „Nö“, „Auflegen“, „Abbrechen“ und
„Tschüss“ beenden den Dialog bei ausreichend sicherer Erkennung.

Standardwerte: 1 s Begrüßungspause, 3 s Rückrufpause, 8 s Zuhörzeit, 2 aufeinander
folgende Verständnisfehler, 120 s maximale Gesprächsdauer. Nach normalen Ansagen
kommt ein kurzer Signalton; nach einer Abschiedsansage wird direkt aufgelegt.
Während Ansagen und Befehlsausführung werden keine Sprachbefehle ausgewertet.

Die Nachfrage nennt aktuell fest „Haustür öffnen“, auch wenn nur andere Aktionen
aktiviert sind. Namen, verfügbare Ziele und Erfolgsansagen sind variabel; die
übrigen hier gezeigten Ansagetexte stehen derzeit in `src/voice_home/dialog.py`.
Zusätzliche YAML-Aktionen bringen ihre eigene Erfolgsansage mit.
