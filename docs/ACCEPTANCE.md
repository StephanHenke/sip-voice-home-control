# Abnahme vor produktiver Gerätefreigabe

## Automatisch

- [ ] `pytest -q` erfolgreich.
- [ ] `voice-home --config config.yaml validate` erfolgreich.
- [ ] Container gebaut; `pjsua2`, `vosk`, `piper` und SIP-Adapter importierbar.
- [ ] `doctor` erreicht openHAB und alle aktivierten Items lesend.

## Telefonie ohne physische Aktionen

- [ ] `register --seconds 15` meldet `registration_success: true`.
- [ ] Beidseitiges Audio mit tatsächlichem SIP/RTP-Netz und Uhr prüfen.
- [ ] Name passt zur konfigurierten Nummer; unbekannte/unterdrückte Nummer abweisen.
- [ ] Callback weist eingehenden Anruf ab und wählt nur den gespeicherten Anschluss.
- [ ] Gefälschte erlaubte Caller-ID ergibt keinen Dialog auf eingehendem Gespräch.
- [ ] SIP-Redirect/REFER/Replaces erzeugt weder fremdes Ziel noch neuen Dialog.
- [ ] Ablehnung, Besetzt und Nichterreichbarkeit ergeben keine Aktion/Wahlwiederholung.
- [ ] Wiederholte INVITEs und erneute Anrufe ergeben keine parallelen Rückrufe.
- [ ] Rückruflimits gelten auch nach Neustart; während Rückruf kein zweiter Anruf.
- [ ] Rückrufpause und Begrüßungspause separat mit 0/1000/2500 ms prüfen.
- [ ] Vor Gesprächsannahme und während Ansagen werden keine Befehle ausgewertet.
- [ ] Auflegen während Pause, Ansage oder Ausführung räumt Gesprächszustand auf.
- [ ] Verbindungsabbruch und spätere Wiederanmeldung funktionieren.

## Sprache und Geräte

- [ ] Alle Tür-/Haustür-Varianten und Bitte-Positionen mit realen Stimmen prüfen.
- [ ] Negationen, Fremdsprache, Hintergrundstimmen, Ansage-Echos und Kombinationsbefehle
  lösen keine Aktion aus. Reine Mailboxansage ergibt keine Aktion.
- [ ] Beide Aktionen nacheinander, direkter Folgeauftrag, Ja/Nein, Schweigen und Timeout.
- [ ] Rückmeldung kommt aus dem Gerät und nicht aus autoupdate/Befehlsspiegelung.
- [ ] Kein OK bei altem Zustand, HTTP-Erfolg allein, fehlender Rückmeldung oder Motorfehler.
- [ ] HTTP-Timeout erzeugt keinen erneuten Befehl; spätes Feedback keinen zweiten Versuch.
- [ ] Haustüraktion unter Aufsicht testen; erst danach dauerhaft aktivieren.
- [ ] Torwerte ermitteln, Öffnungsbeginn nachweisen; erst danach Toraktion aktivieren.
- [ ] CPU/RAM sowie p95-Sprechende→Befehl und Feedback→Ansage messen.

Messziel: p95 höchstens 2 s Sprechende→Befehl und 500 ms Feedback→Ansage.
Anzahl der Testanrufe, Uhrmodell, Sprecher, Codec, Netzqualität und CPU dokumentieren.
