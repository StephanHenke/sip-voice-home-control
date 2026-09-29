# Komponenten

Die Anwendung bindet folgende externe Komponenten ein. Deren Lizenztexte und
Modellkarten gelten unabhängig von der noch nicht gewählten Projektlizenz.

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
