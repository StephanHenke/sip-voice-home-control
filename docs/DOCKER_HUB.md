# SIP Voice Home Control

![Telefonanruf von einer Kinderuhr zum Öffnen der Haustür](https://raw.githubusercontent.com/OWNER/sip-voice-home-control/main/docs/assets/voice-home-header.png)

[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsors-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/StephanHenke)
[![Mit PayPal unterstützen](https://img.shields.io/badge/PayPal-Projekt_unterst%C3%BCtzen-0070BA?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/stephanhmoney)

**Dir gefällt das Projekt? Spendiere einen Kaffee und unterstütze die Weiterentwicklung. ☕**

Haustür, Garagentor oder Licht per Telefon steuern – beispielsweise mit einer
Kinderuhr, auf der sich keine zusätzliche Smart-Home-App installieren lässt.
Der Controller registriert sich per SIP an einer FRITZ!Box, verarbeitet deutsche
Sprachbefehle lokal auf der CPU und führt konfigurierte Aktionen in openHAB aus.

- Freigegebene Rufnummern und persönliche Begrüßungen
- Optionaler Rückruf an eine fest konfigurierte Nummer als Schutz gegen einen
  direkten Zugriff allein durch gefälschte Caller-ID
- Bestätigungsfragen pro Aktion und Rückmeldung anhand konfigurierter Itemzustände
- HTTPS-Oberfläche für Status, YAML-Konfiguration, Logs und Passwortänderung
- Lokale Spracherkennung und Sprachausgabe ohne Sprach-Cloud

## Bereitstellung mit Proxmox Easy Start

Voraussetzungen: Proxmox auf amd64, Root-Konsole, DHCP, Internet für Installation
und Image-Download sowie erreichbare SIP-/RTP- und openHAB-Verbindungen.

Auf dem Host in der interaktiven Root-Konsole starten:

```bash
wget -qO- https://raw.githubusercontent.com/OWNER/sip-voice-home-control/main/deploy/lxc/easy-start.sh | sh
```

1. Im Menü „Neuen LXC installieren“ wählen. LXC-ID, Storage, Netzwerkbrücke,
   Debian-Vorlage und Image `DOCKERHUB_NAMESPACE/sip-voice-home-control:latest` auswählen.
2. Ein eigenes Webpasswort vergeben. Danach richtet der Installer einen neuen
   unprivilegierten LXC mit Docker ein und startet das Image.
3. Die ausgegebene HTTPS-Adresse öffnen, anmelden und SIP, openHAB, Anrufer und
   Aktionen im YAML-Editor konfigurieren, validieren, speichern und neu laden.

Der LXC erhält 2 CPUs, 3 GiB RAM und 12 GiB Disk. Das Webpasswort wird als
gesalzener scrypt-Hash gespeichert; es gibt kein Standardpasswort. Anrufe und
Geräteaktionen bleiben bis zur Einrichtung gesperrt. Ein nicht gesunder
SIP-Status ist vor der vollständigen Konfiguration zu erwarten.

[Ausführliche Easy-Start-Anleitung](https://github.com/OWNER/sip-voice-home-control/blob/main/docs/EASY_START.md)

## Docker auf einem vorhandenen Linux-Host

Das Image ist für **linux/amd64** gebaut. Zum Herunterladen:

```bash
docker pull DOCKERHUB_NAMESPACE/sip-voice-home-control:latest
```

Der Pull allein startet noch keinen Dienst. Für den Betrieb werden die
Compose-Vorlagen, eine passende YAML-Konfiguration und persistente Mounts
benötigt. Die optionale Weboberfläche benötigt zusätzlich TLS-Zertifikat,
Schlüssel und ein per Konsole gesetztes Passwort.

[Docker-/LXC-Konfiguration](https://github.com/OWNER/sip-voice-home-control/blob/main/docs/LXC.md)
 · [Weboberfläche](https://github.com/OWNER/sip-voice-home-control/blob/main/docs/WEB_UI.md)

## Aktualisieren

Den Einzeiler erneut auf Proxmox oder im eingerichteten LXC starten und das
Update-Menü wählen. Auf Proxmox werden laufende lokale Controller-LXC angeboten.
Im LXC stehen zusätzlich **Webpasswort zurücksetzen** und **Einstellungen
zurücksetzen** zur Verfügung. Ein Einstellungsreset erfordert `RESET`, sichert
die bisherige YAML geschützt und sperrt Anrufe und Aktionen. Passwort, TLS und
separate Secret-Dateien bleiben erhalten. Intern wird fehlendes Python bei
Bedarf installiert; Eingaben erfolgen über `/dev/tty`.

Bei einer Easy-Start-Installation zuerst die Anrufannahme deaktivieren und das
Gesprächsende abwarten. Anschließend **im LXC**:

```bash
cd /opt/sip-voice-home
./voice-home-deploy.sh update DOCKERHUB_NAMESPACE/sip-voice-home-control:latest
```

Konfiguration, Webpasswort und Daten bleiben erhalten. `latest` folgt dem
veröffentlichten Stand von `main`; für einen festen Stand einen vorhandenen
`sha-…`-Tag oder Image-Digest verwenden.

## Projekt unterstützen

Dir gefällt SIP Voice Home Control? Mit einem Kaffee kannst du die
Weiterentwicklung freiwillig unterstützen. ☕

[Über GitHub Sponsors unterstützen](https://github.com/sponsors/StephanHenke) ·
[Über PayPal unterstützen](https://paypal.me/stephanhmoney)

## Hinweise und Lizenz

Easy Start wurde automatisiert und mit einer vollständigen Erstinstallation in
einem separaten Proxmox-LXC geprüft. Die eigene Telefonie- und Geräteanbindung
ist vor Ort abzunehmen. Nutzung in eigener Verantwortung. Tür- und Toraktionen
erst nach eigenen Tests freigeben; die Verwaltungsoberfläche nur im vorgesehenen
Verwaltungsnetz erreichbar machen.

GNU GPL-3.0-or-later. Bibliotheken und Sprachmodelle behalten ihre jeweiligen
Lizenzen: [LICENSE](https://github.com/OWNER/sip-voice-home-control/blob/main/LICENSE)
 · [THIRD_PARTY.md](https://github.com/OWNER/sip-voice-home-control/blob/main/THIRD_PARTY.md).

