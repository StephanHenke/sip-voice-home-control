# Docker im unprivilegierten Proxmox-LXC

Die Skripte unter `deploy/lxc` verwalten einen dedizierten Debian-LXC und dessen
Controller. Sie aktivieren keine Tür-/Toraktionen für einen Test.

## Erstinstallation

Auf einem Proxmox-Knoten eine freie ID, einen vorhandenen Debian-Templatepfad,
Storage und Bridge auswählen. Beispiel (IDs und Storage vorher prüfen):

```bash
bash provision-lxc.sh 200 local:vztmpl/DEBIAN-TEMPLATE.tar.zst local-lvm vmbr0
```

Das Skript verweigert belegte IDs. Es erstellt einen unprivilegierten LXC mit
2 CPU-Kernen, 3 GiB RAM (davon maximal 2 GiB für den Controller), 12 GiB Disk,
DHCP, Autostart und den Docker-Funktionen nesting/keyctl. Docker-Pakete kommen
aus dem offiziellen Docker-Repository. AppArmor bleibt aktiviert.

Vor dem Anlegen fragt das Skript das Web-Admin-Passwort zweimal verdeckt ab.
Ein leeres Passwort, eine abweichende Wiederholung oder eine fehlende interaktive
Konsole bricht die Installation ab. Nur ein zufällig gesalzener scrypt-Hash wird
in `/opt/sip-voice-home/web/password.json` gespeichert (UID/GID 10001, Modus 0600).
Das Klartextpasswort wird weder in eine Datei noch in Kommandozeilenargumente
oder Umgebungsvariablen geschrieben. Ohne gesetztes Passwort ist kein Web-Login
möglich; es gibt kein Standardpasswort. Die optionale Oberfläche wird wie in
[WEB_UI.md](WEB_UI.md) mit Compose-Erweiterung und TLS-Zertifikat aktiviert.

In `/opt/sip-voice-home` die Dateien `compose.yaml` und `voice-home-deploy.sh`
ablegen. Persönliche YAML nach `config/config.yaml`, Secrets nach `secrets/`
kopieren. Verzeichnisse gehören UID/GID 10001, Secret-Dateien erhalten Modus 0640.
Eine DHCP-Reservierung ist vor Dauerbetrieb sinnvoll. `sip.public_address` muss
die tatsächlich erreichbare LXC-IP enthalten.

Im LXC `docker login -u BENUTZER` ausführen. Token niemals in Git oder Befehlszeilen
schreiben. Der Docker-Login wird im LXC gespeichert und gehört zum Backup-Schutz.

```bash
cd /opt/sip-voice-home
chmod 700 voice-home-deploy.sh
./voice-home-deploy.sh update your-account/sip-voice-home-control:latest
./voice-home-deploy.sh status
```

## Konfiguration und Updates

YAML und Secrets liegen außerhalb des Docker-Containers. Das gesamte
Konfigurationsverzeichnis wird read-only eingebunden; auch ein atomarer Austausch
der YAML auf dem LXC ist damit sichtbar. Änderungen werden beim Neustart geladen.
Updates überschreiben weder YAML noch Secrets noch Ansagencache.

Vor einem Update die Anrufannahme über die konfigurierte openHAB-Steuerung
ausschalten und das Gespräch beenden lassen. Bei noch nicht eingerichteter
Steuerung bleibt `call_control.initial_accepting: false` für die Abnahme gesetzt.
Das Skript verweigert den Austausch bei aktivierter Annahme, Beschäftigung oder
veraltetem Status. Es prüft das neue Image und openHAB vor dem Austausch.

```bash
./voice-home-deploy.sh check
./voice-home-deploy.sh update              # gespeichertes Image erneut laden
./voice-home-deploy.sh update IMAGE@sha256:DIGEST
./voice-home-deploy.sh apply               # YAML mit vorhandenem Image anwenden
```

Bei fehlgeschlagener Gesundheitsprüfung wird das vorherige Image wieder gestartet,
soweit eines lief. Die YAML wird dabei ausdrücklich nicht zurückgesetzt; eine
defekte Konfiguration muss korrigiert werden. Ein Erstlauf ohne Vorgänger wird bei
Fehlschlag gestoppt. Alte Images bleiben für eine Rückkehr erhalten.

`stage IMAGE` dient ausschließlich der Inbetriebnahme ohne funktionierendes SIP:
Annahme muss ausgeschaltet sein, Konfiguration/openHAB und Sprachbereitschaft
werden geprüft. Dieser Modus erklärt einen SIP-Fehler **nicht** für gesund.

Die Compose-Datei verwendet Docker-Logging `none`. Für einen schreibarmen Betrieb
zusätzlich `logging: {level: OFF, target: none}` in der YAML setzen. `/tmp` ist
tmpfs, `/data` der dauerhafte Ansagencache. LXC-/Host-Betriebslogs sind separat.

## Netzwerk und Abnahme

SIP/TCP zum konfigurierten FRITZ!Box-Port und RTP/UDP müssen in beide benötigten
Richtungen erreichbar sein. Keine zweite Instanz mit denselben SIP-Zugangsdaten
parallel starten. Zuerst `doctor`, dann Registrierung, dann einen vom Benutzer
ausgelösten Anruf testen. Physische Aktionen nur durch den Benutzer vor Ort.

Automatische Image-Veröffentlichung aktualisiert diesen LXC nicht selbstständig.
Updates werden bewusst mit dem Skript gestartet. Backup/HA-Mitgliedschaft werden
durch das Provisioning nicht verändert.
