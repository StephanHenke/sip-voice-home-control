# Verifikation und Abnahme

Die automatisierten Prüfungen laufen im GitHub-Actions-Workflow. Persönliche
Installationsprotokolle, Rufnummern, Hostnamen und Geräteverläufe gehören nicht
in dieses Repository. Aktuelle Testergebnisse stehen im jeweiligen CI-Lauf.

## Lokal prüfen

```bash
pip install -e '.[test]'
pytest -q
voice-home --config config.example.yaml validate
bash -n deploy/lxc/provision-lxc.sh
git diff --check
```

Die Tests prüfen unter anderem Rufnummernnormalisierung, Anrufzulassung,
Rückruflimits, Sprachdialog, Bestätigungen, Gerätestatus, Adapterverbindungen,
Protokollierung und Webzugriff. Testdaten sind synthetisch. Netzwerkzugriffe
werden in den Python-Tests durch lokale Testserver oder Testadapter ersetzt.

## Container prüfen

Der CI-Workflow baut das Image und prüft anschließend native Audioverarbeitung
und synthetische deutsche Sprache ohne Netzwerkzugriff. Die Definition der
aktuellen Prüfungen steht in `.github/workflows/ci.yml`.

## Installation abnehmen

Automatisierte Tests ersetzen keine Abnahme der eigenen Installation.
[ACCEPTANCE.md](ACCEPTANCE.md) beschreibt Tests für SIP, Audio, Gerätefeedback,
Konfigurationspersistenz und Fehlerfälle. Reale Geräteaktionen ausschließlich
beaufsichtigt und durch einen bewusst ausgelösten Test prüfen. Messergebnisse
und persönliche Diagnosen außerhalb des Repositorys aufbewahren.
