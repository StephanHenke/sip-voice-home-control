# HTTPS-Konfigurationsoberfläche

Die optionale Oberfläche bietet einen YAML-Editor mit Zeilenanzeige und farbiger
Syntaxansicht, Validierung, Speichern, Upload, Downloads und 20 Vorgängerversionen.
Sie zeigt Betriebszustand, SIP-Rückmeldecode, Adapter und Gesprächsaktivität sowie
einen kleinen RAM-Logpuffer. Es gibt ein Administrator-Konto ohne Benutzernamen.

## Navigation

Die gemeinsame Navigation führt zu vier separaten Ansichten: **Status**, **Config**,
**Log** und **Passwort ändern**. **Logout** ist auf jeder Ansicht erreichbar.
Direktlinks sind `/#status`, `/#config`, `/#log` und `/#password`; die Zurück-/Vorwärts-
Funktion des Browsers wechselt ebenfalls zwischen den Ansichten. Ungespeicherte
YAML-Änderungen bleiben beim Seitenwechsel erhalten. Logout fragt vor dem Verwerfen
solcher Änderungen nach. Status und Logs werden nur in der jeweiligen Ansicht
alle drei Sekunden aktualisiert.

## LXC einrichten

`deploy/lxc/compose.web.yaml` zusätzlich neben die LXC-Compose-Datei legen.
Das Bereitstellungsskript berücksichtigt sie automatisch. Sie startet den Befehl
`web` und bindet `/config` schreibbar sowie `/web` für Passwort und TLS ein.
Secrets bleiben separat read-only. Es wird kein Docker-Socket eingebunden.

Unter `/opt/sip-voice-home/web` müssen `tls.crt` und `tls.key` vorhanden und für
UID 10001 lesbar sein. Ein Zertifikat der eigenen CA ist vorzuziehen. Bei einem selbstsignierten Zertifikat muss die LXC-IP im SAN stehen;
der Browser vertraut diesem erst nach einer bewussten Einrichtung durch den Benutzer.
Zertifikat und Schlüssel können später ausgetauscht und der Container neu gestartet
werden. HTTPS-Port ist 8443; nur aus dem vorgesehenen Verwaltungsnetz freigeben.
Bei DHCP die LXC-IP reservieren, sonst Zertifikat und SIP-Adresse anpassen.

## Erster Login und Passwortänderung

Es gibt kein Standardpasswort. Ohne gesetztes Passwort bleibt die Anmeldung
gesperrt — auch ein leerer Wert oder `admin` ermöglicht keinen Erstzugang.
Das LXC-Installationsskript fragt vor dem Anlegen des Containers das gewünschte
Webpasswort zweimal verdeckt ab. Bei leerer Eingabe, abweichender Wiederholung
oder fehlender interaktiver Konsole bricht es vor dem Anlegen ab.
Es überträgt ausschließlich einen gesalzenen scrypt-Hash in die Passwortdatei.
Bei manueller Installation muss das Passwort zunächst per Konsole gesetzt werden.
Leere Passwörter sind nicht zulässig, die Höchstlänge beträgt 1024 Zeichen.
Ein bereits gesetztes Passwort wird bei Updates und Neustarts niemals überschrieben.
Das gilt auch für den früher automatisch angelegten Wert `admin`: Bestehende
Installationen müssen diesen einmal per Konsole oder Passwortänderung ersetzen.

Später kann es über **Passwort ändern** unter Angabe des aktuellen Passworts
geändert werden. Jede Änderung beendet alle Web-Sitzungen; danach neu anmelden.
Die erste Einrichtung zeitnah im vorgesehenen Verwaltungsnetz abschließen.

## Passwort per Konsole setzen oder zurücksetzen

Auf dem Proxmox-Knoten interaktiv den LXC betreten (Beispiel-ID ersetzen):

```bash
pct enter 200
docker exec -it -u 10001 sip-voice-home-controller-1 voice-home web-password
```

Der Befehl fragt das neue Passwort zweimal verdeckt ab.
Es wird nur ein gesalzener scrypt-Hash in `/web/password.json` gespeichert.
Kein Passwort in YAML, Kommandozeile oder Chat eintragen. Derselbe Befehl setzt
ein vergessenes Passwort zurück. Alle bisherigen Web-Sitzungen werden dadurch
ungültig, ein Container-Neustart ist dafür nicht erforderlich. Die Datei übersteht
Image-Updates. Fehlt die Datei oder ist sie leer/ungültig, ist die Anmeldung gesperrt.
Ein Neustart legt kein Ersatzpasswort an. Nach versehentlichem Löschen kann derselbe
Konsolenbefehl wieder ein Passwort setzen.

Vor dem ersten Start funktioniert das Setzen auch mit einem temporären Container:

```bash
cd /opt/sip-voice-home
docker compose --project-name sip-voice-home -f compose.yaml -f compose.web.yaml run --rm --no-deps controller web-password
```

Aufruf: `https://CONTROLLER-IP:8443` (durch die eigene Controller-Adresse ersetzen).
Sitzungen liegen im RAM, gelten eine Stunde und enden beim Neustart. Cookies sind
Secure/HttpOnly/SameSite=Strict; Schreibaktionen verlangen einen CSRF-Token.
Fehlversuche sind auf fünf pro Minute und Quelladresse begrenzt.

## Arbeitsablauf

1. Anmelden und YAML bearbeiten oder hochladen. Upload verändert zunächst nur
   den Editor. Dateien sind auf 256 KiB begrenzt.
2. **Validieren** prüft YAML-Syntax, vorhandene Konfigurationsregeln und Lesbarkeit
   der Secret-Dateien. Das ist kein SIP-Anruf und kein Gerätefunktionstest.
3. **Speichern** validiert erneut, sichert den bisherigen Stand und ersetzt die
   YAML atomar. Bei parallelen Änderungen wird das Speichern abgelehnt, statt
   fremde Änderungen zu überschreiben. Speichern allein ändert den laufenden
   Controller nicht.
4. In openHAB die Anrufannahme OFF schalten und das Gesprächsende abwarten.
5. **Gespeicherte Konfiguration laden · Neustart** wählen. Die Anwendung beendet
   den SIP-Prozess geordnet und anschließend sich selbst. Docker startet den
   Container durch `restart: unless-stopped` erneut. Ohne diese Restart-Policy
   bleibt er stehen. Danach neu anmelden und SIP-/Adapterstatus prüfen.

Die Oberfläche bleibt bei einem gescheiterten Start des SIP-Unterprozesses
erreichbar, damit die Konfiguration korrigiert werden kann. Ein Neustart ist dann
auch ohne frischen SIP-Status erlaubt, wenn der Unterprozess nachweislich beendet ist.
Ein Web-Neustart führt keinen automatischen Rollback der YAML durch.

## Versionen, Secrets und Protokolle

Aktuelle und frühere YAML-Dateien können heruntergeladen werden. Zur Wiederherstellung
eine Version hochladen, prüfen, speichern und neu starten. Die letzten 20
Vorgängerversionen liegen unter `/config/.versions`; ältere werden beim Speichern
entfernt. Diese bewussten Konfigurationsänderungen sind persistente Schreibvorgänge.

Direkt in YAML eingetragene Zugangsdaten sind im authentifizierten Editor und in
Downloads enthalten. Deshalb Secret-Dateien bevorzugen. Sie werden weder vom
Editor gelesen noch in Versionsdownloads aufgenommen. Downloads vertraulich
behandeln. Passwort-Hash und TLS-Schlüssel sind nicht über die Download-API erreichbar.

Die Web-Logkonsole zeigt nur gefilterte Anwendungslogs aus `/tmp/voice-home/web.log`,
mit 64 KiB Rotation und einer Archivdatei, die Anzeige höchstens 32 KiB. `/tmp`
muss tmpfs bleiben. Bei `logging.level: OFF` oder `logging.target: none` werden
keine Web-Logs geschrieben. DEBUG aktiviert keine Audioaufzeichnung. Nach einem
Neustart ist der RAM-Puffer leer. HTTP-Anfragen und Passwortversuche werden nicht
mit Inhalten protokolliert. Docker-Logging bleibt in der LXC-Vorlage ausgeschaltet.

Mit INFO/console ist der RAM-Logpuffer aktiv; der Docker-Treiber none verhindert
eine zusätzliche Konsolen-Logdatei.
