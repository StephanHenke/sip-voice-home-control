# Protokolle und gespeicherte Daten

## Konfigurierbare Protokollierung

```yaml
logging:
  level: INFO
  target: console
```

| Parameter | Standard | Bedeutung |
| --- | --- | --- |
| `logging.level` | `INFO` | `OFF`, `ERROR`, `WARNING`, `INFO`, `DEBUG` |
| `logging.target` | `console` | `none`, `console`, `file`, `syslog` |
| `logging.path` | keiner | Bei file erforderlicher absoluter Dateipfad |
| `logging.max_bytes` | `10485760` | Positive Rotationsgroesse pro Datei |
| `logging.backup_count` | `2` | Positive Anzahl Archivdateien plus aktuelle Datei |
| `logging.host` | keiner | Bei syslog erforderlicher Zielhost |
| `logging.port` | `514` | Syslog-Port 1 bis 65535 |
| `logging.transport` | `udp` | `udp` oder `tcp` (ohne TLS) |
| `logging.facility` | `local0` | `local0` bis `local7` |
| `logging.queue_size` | `1000` | Positive maximale Anzahl wartender Syslog-Meldungen im RAM |

OFF oder none unterdrueckt alle regulaeren Logs. Explizite CLI-Ergebnisse und
knappe Konfigurationsfehler bleiben verfuegbar. Unbekannte Einstellungen fuer
Level/Ziel werden als Konfigurationsfehler abgewiesen.

Konsole schreibt nach stderr. Docker speichert diese Ausgabe im Standard mit
json-file und Rotation 10 MB / 3 Dateien. Es gibt keine Altersgrenze in Tagen.
YAML allein aendert den Docker-Treiber nicht. Die Compose-Ergaenzung
`compose.no-container-logs.yaml` setzt ihn auf none; sie benoetigt Compose >= 2.24.4.
Dies verhindert Docker-Ausgabedateien auch bei file/syslog.

Ein Dateiziel unter `/tmp/voice-home/controller.log` bleibt im Container im RAM.
Andere Ziele benoetigen bei schreibgeschuetztem Container einen beschreibbaren
Mount mit passenden Rechten fuer UID 10001. Groessenrotation hat keine Altersfrist.
Bei einem Schreibfehler wird keine Ersatzdatei angelegt.

Syslog wird asynchron aus einer begrenzten RAM-Warteschlange versendet. UDP
bestaetigt keinen Empfang; TCP nutzt Newline-Framing und begrenzte Socket-Wartezeit.
Bei Verbindungsfehlern gehen betroffene Meldungen verloren. Es gibt keinen
plattenbasierten Puffer; ueberzaehlige/fehlgeschlagene Meldungen werden im
Statusfeld `dropped_logs` gezaehlt. Aufbewahrung am entfernten Server ist dessen
Konfiguration. Der Sprach-/SIP-Thread wartet nicht auf das Netzwerk.

## Welche Inhalte werden protokolliert?

INFO enthaelt Ereignisse zu SIP-Anmeldung, Anrufzustand, erlaubter Quelle,
Rueckrufausloesung und -begrenzung, Dialog-Wartezeiten, Aktions-ID und Ergebnis,
Annahmefreigabe sowie Adapterverbindung. Der Peer kann als IP/Port erscheinen.
WARN/ERROR reduzieren dies auf entsprechende Stoerungen. DEBUG kann technische
Diagnoseereignisse enthalten, schaltet aber keine Audioaufzeichnung oder
Transkription in den Logs ein.

Keine Ausgabe von Passwoertern, Tokens, vollstaendigen SIP-Nachrichten oder
Konfigurationsobjekten. Bekannte Secret-Werte werden zusaetzlich maskiert.
Fremdbibliotheksmeldungen werden ab WARNING nur mit Bibliotheksname gemeldet;
HTTP-URLs und Header werden nicht ausgegeben. Native C-Ausgaben von SIP und
Sprachbibliotheken werden im normalen CLI-Betrieb unterdrueckt. Alte Versionen
konnten HTTP-URLs einschliesslich Itemnamen protokollieren; vorhandene Altlogs
werden dadurch nicht rueckwirkend bereinigt.

## Speicherorte

| Ort | Inhalt | Aufbewahrung |
| --- | --- | --- |
| YAML auf dem Host | Namen, erlaubte Nummern, Items, Einstellungen; optional Secrets | Bis manueller Aenderung/Loeschung |
| Secret-Dateien | Alternativ SIP-Passwort / openHAB-Token | Bis manueller Aenderung/Loeschung |
| Arbeitsspeicher | Annahmefreigabe, Gespraechszustand, Rueckrufbudgets mit Nummern und monotonen Zeitpunkten | Ende des Prozesses; abgelaufene Budgeteintraege werden vorher entfernt |
| `/tmp/voice-home/health.json` | Aktueller Status, keine Nummern oder Gespraechsinhalte | RAM-Snapshot, kein Verlauf und kein Wiederherstellen; Ende des Containers |
| `/data/prompts/<hash>.wav` | Erzeugte Ansagen, persoenliche Begruessungen koennen Namen enthalten | Persistenter Cache ohne Ablaufzeit; alte Texte koennen weiter vorhanden sein |
| `/data/prompts/ready.wav` | Signalton | Persistenter Cache, beim Start erzeugt |
| `/models` im Image | Allgemeine Vosk-/Piper-Sprachmodelle | Image-Lebensdauer; keine persoenlichen Trainingsdaten |
| Logziel | Oben beschriebene Betriebsereignisse | none: keine; Datei/Docker: Rotation; Syslog: Serverkonfiguration |

Es gibt keine normale Gespraechsaufzeichnung und keine dauerhafte Anrufhistorie.
Die bisherige SQLite-Datei wird nicht mehr gelesen oder geschrieben. Beim Upgrade
wird sie samt altem persistentem Status gezielt entfernt; siehe
[Betrieb und Upgrade](OPERATIONS.md). Backups sowie alte Docker- und lokale
Diagnoseprotokolle haben eigene Aufbewahrung und werden nicht automatisch geloescht.

Die vorhandenen lokalen Diagnosewerkzeuge koennen bei ausdruecklicher Aktivierung
abweichend Audio/Transkripte erzeugen. Sie sind nicht Teil des normalen Images oder
Starts. Eine Logstufe DEBUG aktiviert sie nicht. Historische Diagnosedateien im
lokalen `.build`-Verzeichnis bleiben vom Upgrade unberuehrt.

## Abfragen

```bash
docker compose exec controller voice-home status
docker compose exec controller voice-home health
docker compose logs --tail 100 controller
```

Der letzte Befehl ist nur fuer Docker-Konsolenlogging vorgesehen. Bei Treiber none
stehen keine Docker-Ausgabelogs zur Verfuegung. Docker-eigene Verwaltungsdaten,
Host-Logs und moegliches Swap sind keine Anwendungslogs; tmpfs allein garantiert
keinen Ausschluss von Betriebssystem-Swap.

### Optionale Push-Texte

Mit `smarthome.notification_item` und `actions[].notification_text` wird bei
bestätigtem Aktionserfolg ein Text einschließlich konfiguriertem Namen an openHAB
übertragen. Controllerlogs enthalten diesen Text nicht. openHAB-Ereignislogs sowie Cloud-/Mobil-Push-Dienste
können den Text jedoch speichern. Die Controllerwarteschlange ist ausschließlich
im RAM. Details: [Push-Benachrichtigungen](OPENHAB_NOTIFICATIONS.md).
