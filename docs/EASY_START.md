# Easy Start auf Proxmox

`deploy/lxc/easy-start.sh` ist ein geführter Shell-Starter für die **Root-Konsole des
Proxmox-Hosts**. Er enthält den Python-Installer und alle Vorlagen in einer Datei.
Python 3 wird intern weiterhin verwendet und bei Bedarf automatisch über APT
installiert; zusätzliche Python-Pakete sind nicht nötig. Unterstützt wird amd64
mit einer Debian-12- oder Debian-13-Vorlage.
Der Installer nutzt die Proxmox-Werkzeuge `pvesh`, `pveam` und `pct`.

## Einzeiler und Menüs

In der interaktiven Root-Konsole des Proxmox-Hosts oder des eingerichteten LXC
ausführen (`OWNER` ersetzen, `wget` muss installiert sein):

```sh
wget -qO- https://raw.githubusercontent.com/OWNER/sip-voice-home-control/main/deploy/lxc/easy-start.sh | sh
```

Die komplette Einrichtung ist enthalten. Eingaben und Passwörter werden von
`/dev/tty` gelesen, getrennt vom heruntergeladenen Skript. Ohne Terminal ist
kein Betrieb möglich. Der vollständige Funktionsblock muss geladen sein, bevor
die Einrichtung beginnt. Quelle vor Ausführung als root prüfen.

Auf Proxmox erscheint:

```text
1) Neuen LXC installieren
2) Installation aktualisieren
3) Status anzeigen
0) Beenden
```

Im eingerichteten LXC erscheint:

```text
1) Controller aktualisieren
2) Webpasswort zurücksetzen
3) Einstellungen zurücksetzen
0) Beenden
```

Gemeint ist die LXC-Konsole, nicht der Docker-Anwendungscontainer. Die Installation
wird über `/opt/sip-voice-home/compose.yaml`, das Bereitstellungsskript und Docker
erkannt. Unbekannte Umgebungen werden vor einer Paketinstallation abgelehnt.
Auf Proxmox werden nur laufende Controller-LXC des aktuellen Knotens angeboten;
gestoppte Container zuerst bewusst starten, für andere Knoten dort anmelden.

## Einzeldatei starten

`deploy/lxc/easy-start.sh` herunterladen und auf den Proxmox-Host kopieren.
Der Installer enthält alle benötigten Vorlagen bereits: LXC-Einrichtung,
Compose-Dateien, Startkonfiguration und Update-Skript. Ein Repository-Checkout
oder das Nachladen weiterer Quelldateien über die GitHub-API ist nicht nötig.

Auf der interaktiven Proxmox-Root-Konsole starten:

```bash
bash easy-start.sh
```

Ohne Argumente öffnet sich das Menü. Bei der Installation wird das Container-Image
abgefragt; ohne Tag wird `latest` verwendet. Direkt installieren:

```bash
sh easy-start.sh --install --image ghcr.io/OWNER/sip-voice-home-control:latest
```

Explizite Tags und Digests bleiben erhalten. Für reproduzierbare Installationen
eine bestimmte Installer-Version und einen festen Image-Digest verwenden.
`--repository OWNER/sip-voice-home-control` bleibt als Kurzform für den GHCR-Namen
verfügbar; damit erfolgt kein Zugriff auf das Quellrepository.

**Nur bei öffentlich erreichbarer Skriptdatei** ist dieser Start direkt von GitHub
möglich. Er führt heruntergeladenen Code als root aus; Quelle zuvor prüfen:

```bash
(
  set -e
  if ! command -v curl >/dev/null 2>&1; then
    apt-get update
    apt-get install -y curl ca-certificates
  fi
  installer="$(mktemp)"
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://raw.githubusercontent.com/OWNER/sip-voice-home-control/main/deploy/lxc/easy-start.sh -o "$installer"
  bash "$installer" --repository OWNER/sip-voice-home-control
)
```

Ein privates Repository liefert ohne Anmeldung keinen anonymen Download.
In diesem Fall die Einzeldatei über die angemeldete GitHub-Oberfläche herunterladen
und auf den Host kopieren. Tokens nicht in URLs, Befehlszeilen oder Shell-History
eintragen. Der Installer gehört zu diesem Projekt und ist keine Veröffentlichung
des Community-Helper-Scripts-Projekts.

Pipe-Aufrufe sind unterstützt, benötigen aber eine interaktive Root-Konsole.
Der Shell-Starter prüft Root-Zugriff, Proxmox-Werkzeuge und
Architektur vor der Python-Installation. Bei APT-Fehlern bricht er ab; bestehende
Paketquellen bleiben unverändert. Der temporär entpackte Python-Installer wird
nach Programmende entfernt. `bash easy-start.sh --help` zeigt die Hilfe ohne
Installation. Der direkte Aufruf von `easy-start.py` bleibt ebenfalls möglich.

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
scrypt-Hash. Das Webpasswort wird vor der LXC-Erstellung, der Docker-Installation
und dem Image-Pull verlangt. Ohne Passwort bleibt die Installation gesperrt.

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
Alternativ den Einzeiler erneut starten und das Update-Menü wählen. Auf dem
Host eine lokale LXC-ID auswählen, im LXC wird die dortige Installation verwendet.
Das Ziel-Image wird abgefragt, die aktuelle Image-ID angezeigt und vor dem Update
`UPDATE` verlangt. Ohne Tag wird `latest` verwendet. Direkter Aufruf:

```sh
# Proxmox-Host, Beispiel-ID ersetzen:
sh easy-start.sh --update 200 --image ghcr.io/OWNER/sip-voice-home-control:latest
# Im LXC:
sh easy-start.sh --update --image ghcr.io/OWNER/sip-voice-home-control:latest
```

Bei Pipe-Aufrufen Optionen mit `| sh -s -- --update ...` übergeben.
Aktualisiert wird der Controller, nicht Proxmox, Debian oder Docker. Ein fehlender
oder veralteter Status, ein Gespräch oder aktivierte Annahme blockieren das Update.
Das vorhandene Update-Skript prüft Konfiguration und Geräteanbindung ohne
Gerätebefehle. Bei fehlgeschlagener Betriebsprüfung wird das vorherige Image
wieder gestartet; ein fehlgeschlagener Rollback wird als Fehler gemeldet.
Updates benötigen eine vollständig eingerichtete, prüfbare Installation.

## Passwort und Einstellungen zurücksetzen

Nur das LXC-Menü bietet die beiden Reset-Funktionen an. Beim Passwortreset wird
das neue Webpasswort zweimal verdeckt abgefragt und als scrypt-Hash gespeichert.
Bestehende Web-Sitzungen werden ungültig; Konfiguration und TLS bleiben erhalten.

Der Einstellungsreset benötigt eine vorhandene Weboberfläche, einen aktuellen
freien Betriebsstatus und ausgeschaltete Annahme. `RESET` muss ausdrücklich
eingegeben werden. Vor Änderungen wird die YAML unter
`/opt/sip-voice-home/backups/config-reset-<Zufalls-ID>.yaml` gesichert (Verzeichnis
0700, Datei 0600, root). Die Sicherung kann Zugangsdaten enthalten und wird nicht
automatisch gelöscht. Sie ist kein Download in der Weboberfläche.

Anschließend wird der Controller gestoppt, die YAML atomar durch die gesperrte
Startkonfiguration ersetzt und der Controller wieder gestartet. Bei einem
erkannten Startfehler wird die vorherige YAML wiederhergestellt. Die Prüfung
nach dem Reset kontrolliert den lokalen Webport, nicht eine SIP-Anmeldung.
Das Webpasswort, TLS, separate Secrets, Ansagencache und bestehende YAML-Versionen
bleiben erhalten. Dies ist keine Datenlöschung. SIP bleibt bis zur erneuten
Einrichtung ungesund; Anrufer und Geräteaktionen sind nicht freigegeben.

Reset und Deployment verwenden dieselbe Wartungssperre. Während der Wartung
keine parallelen Änderungen im Webeditor oder über openHAB vornehmen.

Bei Abbruch wird ein bereits angelegter LXC nicht automatisch gelöscht. Die
ausgegebene ID auf dem Host prüfen; bestehende Container werden nicht überschrieben.
DHCP/DNS, Internetzugriff auf Paketquellen/Template-Server/Registry sowie freie Kapazität
auf den gewählten Storages sind Voraussetzungen. Port 8443 nur im vorgesehenen
Verwaltungsnetz erreichbar machen. Das Skript ändert keine Router-Firewallregeln.

Automatisierte Tests prüfen die Auswahlgrenzen, den Passwortablauf, die gesperrte
Startkonfiguration und Befehlsübergabe mit ersetzten Infrastrukturaufrufen.
Zusätzlich wurde die vollständige Neuanlage per Shell-Pipe in einem separaten
unprivilegierten LXC auf Proxmox geprüft, einschließlich Docker-Installation,
Image-Download und HTTPS-Erreichbarkeit. SIP und openHAB wurden für die
Wartungstests durch lokale Testgegenstellen ersetzt; reale Geräte wurden nicht
angesteuert. Geprüft wurden auch Passwortreset, Image-Update mit Erhalt von YAML,
Passwort und TLS, Rückkehr zum vorherigen Image bei einem absichtlich defekten
Kandidaten sowie Einstellungsreset mit geschützter Sicherung und gesperrter
Startkonfiguration. Die eigene Netzwerk- und Telefonieanbindung bleibt vor Ort
zu prüfen.

Referenz: [Proxmox-Containerdokumentation](https://pve.proxmox.com/pve-docs/chapter-pct.html).

## Vorlagen weiterentwickeln

Optional können Entwickler mit `--source-dir .` die Dateien eines lokalen
Checkouts statt der eingebetteten Vorlagen verwenden. Nach Änderungen an diesen
Vorlagen den Einzeldatei-Installer im Repository neu erzeugen:

```bash
python3 scripts/bundle_installer.py
```

Ein automatisierter Test prüft, dass die eingebetteten Dateien mit den überprüften
Quelldateien übereinstimmen.
