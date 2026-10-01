# Easy Start auf Proxmox

`deploy/lxc/easy-start.py` ist ein geführter Installer für die **Root-Konsole des
Proxmox-Hosts**. Er benötigt Python 3 aus Proxmox und keine zusätzlichen
Python-Pakete. Unterstützt wird amd64 mit einer Debian-12- oder Debian-13-Vorlage.
Der Installer nutzt die Proxmox-Werkzeuge `pvesh`, `pveam` und `pct`.

## Start aus einem vorhandenen Checkout

Repository auf den Proxmox-Host kopieren oder dort mit den eigenen
GitHub-Zugriffsrechten klonen. Im Repository-Verzeichnis starten:

```bash
python3 deploy/lxc/easy-start.py --source-dir .
```

In diesem Modus stammen alle Installationsdateien aus dem Checkout. Das gewünschte
Registry-Image wird abgefragt, beispielsweise
`ghcr.io/OWNER/sip-voice-home-control:latest` (OWNER in Kleinschreibung ersetzen).

## Einzeldatei / Download-Start

Es genügt auch, `deploy/lxc/easy-start.py` herunterzuladen und auf den Proxmox-Host
zu kopieren. Es lädt seine Begleitdateien selbst. `OWNER` ersetzen:

```bash
python3 easy-start.py --repository OWNER/sip-voice-home-control
```

Bei einem privaten Repository fragt der Assistent bei Bedarf einen GitHub-Token
mit Lesezugriff verdeckt ab. Dieser bleibt im RAM. Für einen bestimmten Quellstand
`--ref COMMIT_ODER_TAG` ergänzen. Ein Branch wird zuerst zu einer Commit-ID aufgelöst;
alle Begleitdateien stammen anschließend aus genau diesem Commit.

**Nur bei öffentlich erreichbarer Skriptdatei** ist dieser Start direkt von GitHub
möglich. Er führt heruntergeladenen Code als root aus; Quelle zuvor prüfen:

```bash
(
  set -e
  installer="$(mktemp)"
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://raw.githubusercontent.com/OWNER/sip-voice-home-control/main/deploy/lxc/easy-start.py -o "$installer"
  python3 "$installer" --repository OWNER/sip-voice-home-control
)
```

Ein privates Repository liefert ohne Anmeldung keinen anonymen Download.
In diesem Fall die Einzeldatei über die angemeldete GitHub-Oberfläche herunterladen
oder den Checkout verwenden. Tokens nicht in URLs, Befehlszeilen oder Shell-History
eintragen. Der Installer gehört zu diesem Projekt und ist keine Veröffentlichung
des Community-Helper-Scripts-Projekts.

## Geführter Ablauf

1. Freie LXC-ID vorschlagen; belegte IDs zurückweisen.
2. Aktiven Storage für Root-Dateisystem und Template sowie Netzwerkbrücke auswählen.
3. Debian-Vorlage aus dem Proxmox-Katalog wählen und herunterladen.
4. Container-Image wählen und die Zusammenfassung mit `INSTALL` bestätigen.
5. Webpasswort zweimal verdeckt eingeben. Ohne Passwort wird kein LXC angelegt.
6. Unprivilegierten LXC erstellen: 2 CPUs, 3 GiB RAM, 12 GiB Disk, DHCP,
   Autostart und Docker-Nesting.
7. Docker Engine und Compose aus dem Docker-Repository installieren.
8. Compose-Dateien, Update-Skript und gesperrte Startkonfiguration einrichten.
9. TLS-Zertifikat mit der DHCP-IP erzeugen, Image laden und Webcontainer starten.
10. HTTPS-Erreichbarkeit und Zugriffssperre prüfen; URL und Zertifikatsfingerabdruck anzeigen.

Falls ein Image nicht öffentlich abrufbar ist, werden Registry-Benutzer und Token
abgefragt. Der Token wird über stdin an `docker login` übergeben. Docker speichert
diesen Login im LXC; ohne Credential-Helper ist das kein verschlüsselter
Passwortspeicher. Der Webpasswortspeicher enthält dagegen ausschließlich Salt und
scrypt-Hash. Repository- und Registry-Berechtigungen sind getrennte Zugriffsrechte.

## Danach im Webeditor

Mit dem selbst gewählten Passwort anmelden. Den angezeigten TLS-Fingerabdruck
prüfen oder ein Zertifikat der eigenen CA installieren; DHCP-Adresse reservieren.

Die Startkonfiguration enthält **kein SIP-Passwort**, keine freigegebenen Anrufer
und keine aktivierten Aktionen. Die Anrufannahme startet ausgeschaltet.
Der Webeditor läuft bereits, während der SIP-Unterprozess wegen der unvollständigen
Konfiguration beendet bleibt. `unhealthy`/unbekannter SIP-Status ist in diesem
Einrichtungszustand zu erwarten und wird nicht als erfolgreicher Telefonbetrieb
ausgewiesen.

SIP- und openHAB-Daten sowie Itemzuordnungen im Editor eintragen, validieren,
speichern und neu laden. Annahme erst nach der [Abnahme](ACCEPTANCE.md) aktivieren.
Bei deaktivierter openHAB-Anrufsteuerung dazu `call_control.initial_accepting`
anpassen und neu laden; alternativ die [openHAB-Steuerung](OPENHAB_CONTROL.md)
einrichten. Bei direkter YAML-Nutzung werden die Zugangsdaten in der lokalen
Konfiguration gespeichert; Secret-Dateien sind ebenfalls möglich.

Der Installer führt keine Telefonanrufe und keine Tür-/Torbefehle aus.
Ein erfolgreicher Web-Start beweist noch keine SIP-, RTP- oder openHAB-Verbindung.

## Updates und Fehlerfälle

Im LXC nach vollständiger Konfiguration:

```bash
cd /opt/sip-voice-home
./voice-home-deploy.sh update ghcr.io/OWNER/sip-voice-home-control:latest
```

Annahme vorher ausschalten und Gesprächsende abwarten. Das vorhandene
[Update-Skript](LXC.md) erhält Konfiguration, Webpasswort und Daten.
Der Easy-Start-Assistent selbst dient ausschließlich der Erstinstallation.

Bei Abbruch wird ein bereits angelegter LXC nicht automatisch gelöscht. Die
ausgegebene ID auf dem Host prüfen; bestehende Container werden nicht überschrieben.
DHCP/DNS, Internetzugriff auf Paketquellen/GitHub/Registry sowie freie Kapazität
auf den gewählten Storages sind Voraussetzungen. Port 8443 nur im vorgesehenen
Verwaltungsnetz erreichbar machen. Das Skript ändert keine Router-Firewallregeln.

Automatisierte Tests prüfen die Auswahlgrenzen, den Passwortablauf, die gesperrte
Startkonfiguration und Befehlsübergabe mit ersetzten Infrastrukturaufrufen.
Eine vollständige Neuanlage auf einem realen Proxmox-Host ist separat abzunehmen.

Referenz: [Proxmox-Containerdokumentation](https://pve.proxmox.com/pve-docs/chapter-pct.html).
