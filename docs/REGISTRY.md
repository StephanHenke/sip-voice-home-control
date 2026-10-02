# Automatische Container-Images

Der GitHub-Actions-Workflow baut und veröffentlicht das Image automatisch.
Ein Push auf `main` durchläuft Python-Tests, Konfigurationsprüfung, Docker-Build
und zwei native Sprach-/Audioprüfungen ohne Netzwerk. Erst danach wird genau das
geprüfte Image hochgeladen; vor dem Upload erfolgt kein zweiter Build.

## Images und Tags

- GHCR: `ghcr.io/your-account/sip-voice-home-control`
- Docker Hub: optional `<namespace>/sip-voice-home-control` gemäß Repository-Variable
- `latest`: letzter erfolgreicher Main-Build
- `sha-<vollständiger Commit-SHA>`: Zuordnung zum geprüften Commit
- Git-Tag `v1.2.3`: zusätzlich Image-Tag `1.2.3`; verändert `latest` nicht

Pull Requests und andere Branches werden geprüft, veröffentlichen aber keine Images.
Manueller Start unter Actions → „Test, build and publish container“ → Run workflow;
Veröffentlichung ebenfalls nur für `main` oder einen `v…`-Tag.
Zurzeit wird **linux/amd64** gebaut. ARM64 benötigt einen zusätzlichen Build und
native Prüfung und wird nicht als bereits unterstützt ausgewiesen.

## GitHub Container Registry

Die Anmeldung erfolgt mit dem kurzlebigen `GITHUB_TOKEN` und `packages: write`.
Ein zusätzliches persönliches Token ist für den Workflow nicht notwendig.
Neue persönliche GHCR-Packages sind zunächst privat. Die Pipeline ändert keine
Package-Sichtbarkeit; ein bereits öffentliches Package wird dadurch nicht privat.
Das Image trägt Repository- und Commit-Labels zur Zuordnung.

Privates Image verwenden: einmal `docker login ghcr.io` mit einem geeigneten
Token mit `read:packages`, anschließend beispielsweise:

```bash
docker pull ghcr.io/your-account/sip-voice-home-control:latest
```

## Docker Hub aktivieren

Zuerst im gewünschten Docker-Hub-Konto ein **privates Repository** anlegen bzw.
dessen Sichtbarkeit prüfen. Der Workflow ändert die Sichtbarkeit nicht. Ein
Docker-Hub-Token mit Schreibrecht auf das Repository in GitHub hinterlegen,
nicht in YAML, Quellcode oder Chat.

Unter Repository → Settings → Secrets and variables → Actions setzen:

| Typ | Name | Wert |
| --- | --- | --- |
| Variable | `DOCKERHUB_USERNAME` | Benutzer des Docker-Hub-Tokens |
| Variable | `DOCKERHUB_IMAGE` | Ziel, z. B. `meinname/sip-voice-home-control` |
| Secret | `DOCKERHUB_TOKEN` | Docker-Hub-Zugangstoken |
| Variable | `DOCKERHUB_ENABLED` | Erst nach Einrichtung `true` setzen |

Danach Workflow auf `main` manuell starten oder einen Commit pushen. Ohne diese
Aktivierung wird ausschließlich GHCR verwendet. Bei aktivierter, unvollständiger
Docker-Hub-Konfiguration schlägt die Veröffentlichung verständlich fehl.
Uploads in zwei Registries sind nicht atomar: Bei einem Netzwerkfehler kann eine
Registry bereits aktualisiert sein. Den Lauf dann erneut starten.

## Container aus der Registry starten

Die Ergänzung `compose.registry.yaml` entfernt den lokalen Build und verwendet
das über `VOICE_HOME_IMAGE` angegebene Registry-Image (Compose >= 2.24.4).
`your-account` in den Beispielen durch den eigenen Registry-Namensraum ersetzen.
Ohne explizites Image bricht Compose ab. Mounts, tmpfs, Netzwerk und
Healthcheck aus der Basisdatei bleiben erhalten. Die Ergänzungen für Secret-Dateien
und deaktivierte Docker-Logs lassen sich als weitere `-f`-Dateien kombinieren.

```bash
export VOICE_HOME_IMAGE=ghcr.io/your-account/sip-voice-home-control:latest
docker compose -f compose.yaml -f compose.registry.yaml pull
docker compose -f compose.yaml -f compose.registry.yaml up -d --no-build
```

Für reproduzierbare Installationen einen Commit-Tag oder Registry-Digest verwenden.
Das Ziel lässt sich ohne YAML-Änderung über `VOICE_HOME_IMAGE` wählen, etwa
`ghcr.io/your-account/sip-voice-home-control:1.2.3` oder das eigene Docker-Hub-Image.
Die Befehle funktionieren erst nach dem ersten erfolgreichen Registry-Upload.
Ein Registry-Upload startet vorhandene Installationen **nicht** automatisch neu.
Ein solches Update während eines Telefongesprächs wird damit vermieden.

## Voraussetzungen

Die Vorlage für die Docker-Hub-Übersicht liegt in [DOCKER_HUB.md](DOCKER_HUB.md).
Vor dem Einfügen in Docker Hub `OWNER` durch den GitHub-Eigentümer und
`DOCKERHUB_NAMESPACE` durch den Docker-Hub-Namespace ersetzen. Das Headerbild
benötigt einen öffentlich erreichbaren GitHub-Raw-Link. Die Übersicht wird
derzeit manuell in Docker Hub gepflegt; Image-Pushes aktualisieren sie nicht.

GitHub Actions und die erforderlichen Registry-Berechtigungen müssen aktiviert sein.
Bei ausgeschöpftem Actions-Kontingent muss zunächst wieder Kapazität verfügbar sein.
Ein fehlgeschlagener Lauf kann anschließend manuell neu gestartet werden.
Images stehen erst nach einem erfolgreichen Publish-Lauf zur Verfügung.

Die privaten YAML-Dateien, Secrets, lokalen Diagnosen und Laufzeitdaten bleiben
durch `.dockerignore` aus dem Build-Kontext ausgeschlossen.

Referenzen: [Docker: mehrere Registries](https://docs.docker.com/build/ci/github-actions/push-multi-registries/),
[GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
