# Komponenten

Die Anwendung bindet folgende externe Komponenten ein. Deren Lizenztexte und
Modellkarten gelten unabhängig von der Projektlizenz GPL-3.0-or-later.
Die Projektlizenz lizenziert fremde Komponenten nicht um.

| Komponente | Referenz |
|---|---|
| PJSIP / PJSUA2 2.16 | https://github.com/pjsip/pjproject/tree/2.16 (GPL-2.0-or-later oder separate kommerzielle Lizenz) |
| Vosk 0.3.45 | https://github.com/alphacep/vosk-api (Apache-2.0) |
| Vosk German small 0.15 | https://alphacephei.com/vosk/models (Apache-2.0 laut Modellliste) |
| Piper 1.3.0 | https://github.com/OHF-Voice/piper1-gpl (GPL-3.0) |
| Thorsten medium | https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/de/de_DE/thorsten/medium (mitgelieferte MODEL_CARD beachten) |

Der Modell-Downloader verwendet eine feste Piper-Repository-Revision und speichert
Download-URLs sowie SHA-256-Prüfsummen im Image unter `/models/manifest.json`.
Es werden keine externen Trainingsdaten oder Modelle im Git-Repository gespeichert.

## Weitergabe von Container-Images

Bei Weitergabe eines Images müssen die Lizenz- und Hinweispflichten aller
enthaltenen Komponenten erfüllt werden. Für GPL-Komponenten gehört dazu der
entsprechende Quellcode einschließlich erforderlicher Build-Skripte gemäß der
jeweiligen Lizenz. Diese Übersicht und Links auf fremde Repositories allein
sind kein vollständiger Nachweis der Erfüllung dieser Pflichten.

Vor einer öffentlichen Image-Veröffentlichung sind die tatsächlich eingebauten
Versionen einschließlich transitiver Abhängigkeiten, Lizenztexte und die
zugehörige Quellcodebereitstellung zu prüfen. Die Wahl der Projektlizenz ersetzt
diese Prüfung nicht.
