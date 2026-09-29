# Vereinbarte Anforderungen

- Ein Docker-Container auf Linux/amd64; lokale CPU-Verarbeitung ohne LLM/GPU.
- FRITZ!Box als SIP-Registrar, separate Controller-Rufnummer und explizite Anruferliste.
- Rufnummer und Name werden in einem Eintrag verknüpft. Der Name kommt aus der Konfiguration.
- Begrüßung ohne Aufzählung der verfügbaren Ziele.
- `callback` ist pro Nummer der Standard, `direct` ist ausdrücklich möglich.
- Im Rückrufmodus eingehenden Anruf abweisen, anschließend ausschließlich die gespeicherte
  Nummer zurückrufen. Dialog nur auf diesem Rückruf, keine automatische Wiederholung.
- Standardpausen: Rückruf nach 3 Sekunden, Begrüßung 1 Sekunde nach Annahme; konfigurierbar.
- Rückruf höchstens 30 Sekunden klingeln lassen, mindestens 60 Sekunden Abstand,
  maximal fünf Versuche je Nummer/Stunde, dauerhaft gespeichert.
- Ein Gespräch einschließlich ausstehendem Rückruf, keine Warteschlange.
- Deutsche Satzmuster mit Aliasen: Tür/Haustür und Garage/Garagentor.
- „Aufschließen“ und „Öffnen“ bedeuten bei der Haustür beide Fallenöffnung.
- Optionen zum späteren Hinzufügen von Lichtaktionen über Konfiguration.
- Keine Aktion bei Negation, unsicherem Text, fremdem Ziel oder mehreren Aufträgen.
- Ergebnis nur nach echter neuer Geräterückmeldung: Haustür freigegeben, Tor öffnet sich.
- Torzuordnung zunächst deaktiviert, bis Befehl/Rückmeldung bekannt und geprüft sind.
- Nach Ergebnis weitere Aktionen anbieten. Direkten Folgeauftrag akzeptieren;
  „Ja“ fragt nach, „Nein“/„Auflegen“ beendet den Anruf.
- Acht Sekunden Eingabewartezeit, zwei Fehlversuche, maximal 120 Sekunden Gespräch.
- Keine Aktionen während der Ansage, Bereitschaftston vor der Eingabe.
- Dieselbe Aktion darf im Gespräch mehrfach neu angefordert werden; kein automatischer Wiederholungsversand.
- Optionale Bestätigungsfrage je Aktion, konfigurierbar mit eigenem Text. Nur ein
  explizites Ja führt aus; Nein/Abbrechen verwirft den Auftrag und bietet weitere
  Aktionen an. Auflegen beendet das Gespräch. Jede neue Anforderung wird erneut
  bestätigt, wenn die Bestätigungsfrage eingeschaltet ist.
- Persönliche Konfiguration und Secrets außerhalb von Git und Docker-Build-Kontext.
- Abnahme auf realer Uhr; keine Zusage tatsächlicher Reaktionszeiten vor Messung.

## Bewusste Grenze

Rückrufschutz belegt den Zugang zur hinterlegten Telefonnummer, nicht die Identität
einer bestimmten Person. Telefonnetz-Rufumleitungen, kompromittierte Anschlüsse und
Anrufe, die lediglich Rückrufe auslösen, bleiben relevant. Ein ASR-Konfidenzwert ist
ebenfalls kein Authentifizierungsmerkmal.
