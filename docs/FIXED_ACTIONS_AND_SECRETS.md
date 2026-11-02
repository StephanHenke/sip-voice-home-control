# Feste Anruferaktionen, Formular und verschlüsselte Zugangsdaten

## Eine feste Aktion pro Anrufer

```yaml
callers:
  - number: "+4915123456789"  # Beispielnummer ersetzen
    name: Anna
    access_mode: callback
    fixed_action: front_door_open
    require_confirmation: true
```

`fixed_action` verweist auf die `id` einer vorhandenen Aktion. Ohne dieses Feld
oder bei leerem Wert bleibt der bisherige Sprachdialog unverändert.
Die Aktion muss aktiviert sein, sonst wird eine Fehlermeldung gesprochen und
aufgelegt. Eine unbekannte Kennung wird bei der Validierung abgewiesen.

- `direct`: erst nach bestätigter Annahme, verfügbarer Audioverbindung und
  `dialog.answer_delay_ms` fortfahren.
- `callback`: der ursprüngliche Anruf löst niemals die Geräteaktion aus.
  Erst wenn der konfigurierte Rückruf angenommen wurde und Audio bereit ist,
  beginnt derselbe Ablauf. Klingeln und vorzeitiges Audio reichen nicht.
- Ohne Bestätigung: die feste Aktion genau einmal ausführen, Ergebnis ansagen
  und auflegen. Es kommt keine Begrüßungs-/Aktionsauswahl und keine Folgefrage.
- Mit Bestätigung: `actions[].confirmation_text` vorlesen, Signalton und Ja/Nein
  abwarten. Nein/Abbruch beendet das Gespräch ohne Gerätebefehl. Andere Befehle
  wechseln nicht zu einer anderen Aktion. Schweigen und unklare Antworten
  verwenden die vorhandenen Fehlversuchs- und Gesprächsgrenzen.

Die Bestätigung ist erforderlich, wenn **entweder** die Aktion **oder** der Anrufer
`require_confirmation: true` setzt. Ein Anrufer kann eine an der Aktion verlangte
Bestätigung nicht ausschalten. Der Fragetext darf dann nicht leer sein.
Rufnummernprüfung, Annahmesperre, Rückruflimits, Gerätefeedback und
Benachrichtigungen bleiben wirksam. Nur der feste Ablauf ist auf eine Aktion
beschränkt; normale Dialog-Anrufer können weiterhin alle aktivierten Aktionen nutzen.

## Formular oder YAML

Unter **Config → Formular** sind alle YAML-Anwendungsparameter gruppiert:
SIP, openHAB, Anrufer, Aktionen, Weboberfläche, Dialog, Rückruf, Sprache,
Anrufsteuerung, Adapter und Logs. Neue Anrufer/Aktionen lassen sich hinzufügen
und entfernen. Feste Aktionen werden aus den Aktionskennungen ausgewählt.
Sprachmuster und Wertelisten haben einen Eintrag pro Zeile; Zustandszuordnungen
lassen sich als Name mit Werteliste bearbeiten.

**YAML-Editor** bleibt eine gleichwertige Alternative. Beide Ansichten bearbeiten
denselben Entwurf; erst **Speichern** validiert und schreibt die YAML.
Beim Bearbeiten im Formular wird YAML neu formatiert und Kommentare entfallen.
Ein Wechsel ohne Formularänderung verändert die YAML nicht. Unbekannte Felder
werden nicht still gelöscht; die reguläre Konfigurationsprüfung bleibt zuständig.
YAML-Aliase und doppelte Schlüssel sind nicht zulässig.

Die YAML ist die einzige Konfigurationsquelle, keine zusätzliche Datenbank.
Direkte Dateiänderungen werden nach Neustart gelesen. Uploads, Downloads,
Versionssicherung, Konfliktprüfung und Passwortänderung bleiben verfügbar.
Hosteinstellungen wie Docker-Mounts, TLS-Dateien und Registry-Zugang gehören
weiterhin zur Bereitstellung, nicht zum Anwendungsformular.

## Weboberfläche über YAML deaktivieren

```yaml
web:
  enabled: false
  bind: 0.0.0.0
  port: 8443
```

Beim nächsten Start des Befehls `web` läuft dann ausschließlich der SIP-Dienst:
kein HTTP-/HTTPS-Listener, keine Anmeldung und kein Web-Logpuffer.
Zum Reaktivieren `enabled: true` per Konsole in der YAML setzen und den Container
neu starten. Der Befehl `serve` bleibt immer ohne Weboberfläche, auch bei
`web.enabled: true`. Fehlt der Abschnitt, bleibt bestehendes Verhalten erhalten.

`bind` ist eine lokale IPv4-Adresse, `port` eine ganze Zahl von 1024 bis 65535.
Vorhandene Umgebungsvariablen `VOICE_HOME_WEB_BIND` und `VOICE_HOME_WEB_PORT`
haben Vorrang; bei älteren Compose-Dateien diese Overrides gegebenenfalls
entfernen. TLS-Zertifikat und Webpasswort werden durch Abschalten nicht gelöscht.

## Verschlüsselung

Direkte Werte in `sip.password` und `openhab.token` werden beim Web-Speichern
oder beim Start von `serve`/`web` mit authentifizierter Fernet-Verschlüsselung
ersetzt. Die Felder enthalten danach einen String mit Präfix `enc:v1:`.
Im Betrieb werden die Werte nur im Speicher entschlüsselt. Passwortmaskierung
in Formularfeldern ist zusätzlich aktiv; gespeicherte Werte werden nicht als
entschlüsselter Klartext an den Browser zurückgegeben.

Der Schlüssel liegt standardmäßig in **`.secrets.key` neben der YAML**,
also normalerweise `/config/.secrets.key`, mit Linux-Dateimodus `0600`.
Alternativ kann `VOICE_HOME_SECRETS_KEY_FILE` auf eine separat eingebundene
Schlüsseldatei verweisen. Der Schlüssel wird nicht in YAML-Downloads exportiert.
Ein fehlender/falscher Schlüssel oder veränderte verschlüsselte Daten führen
zum Fehler; es gibt keinen Klartext-Fallback und keinen automatisch erzeugten
Ersatzschlüssel für bereits verschlüsselte Werte.

**Konfiguration und Schlüssel getrennt und geschützt sichern.** Ohne passenden
Schlüssel müssen Zugangsdaten neu eingetragen werden. Wer Hostzugriff auf beide
Dateien hat, kann sie entschlüsseln. Die Funktion schützt insbesondere allein
kopierte YAML-Dateien, nicht einen übernommenen Host.

Das Web-Login-Passwort bleibt ein **gesalzener scrypt-Hash**. Es wird nicht
reversibel verschlüsselt, weil es für die Anmeldung nicht rekonstruiert werden muss.

Beim Start werden auch die lokalen YAML-Versionen in `config/.versions`
auf Inline-Verschlüsselung umgestellt. Neue Versionen enthalten keine Klartext-
Zugangsdaten. Fremde Backups, ältere Downloads, Dateisystemsnapshots und manuell
angelegte Kopien werden nicht bereinigt. Auch Namen, Telefonnummern und Itemnamen
bleiben in der YAML lesbar. Verschlüsselung ist keine sichere Löschung bereits
vorher gespeicherter Daten.

Externe `password_file`-/`token_file`-Dateien bleiben kompatibel und unverändert.
Sie werden nicht automatisch überschrieben; ihre Absicherung bleibt Aufgabe
des jeweiligen Secret-Mounts. Für automatische Verschlüsselung den direkten
Wert im YAML-/Formularfeld verwenden und die alternative Dateiquelle entfernen.

## Upgrade und reiner Dateibetrieb

Automatische Verschlüsselung benötigt ein **beschreibbares Konfigurationsverzeichnis**
für UID 10001. Die neuen Compose-Vorlagen binden `./config:/config` ein;
das restliche Container-Dateisystem bleibt schreibgeschützt. Die Basis-Compose-
Datei erwartet jetzt `config/config.yaml` statt einer einzelnen `config.yaml`.
Bestehende Installationen müssen Mount und Dateirechte entsprechend anpassen.
Die bisherige Web-Compose-Variante hatte bereits einen beschreibbaren Verzeichnismount.

Für einen dauerhaft schreibgeschützten Mount Zugangsdaten zuerst bei gestopptem
Controller mit einem beschreibbaren Mount umstellen:

```sh
voice-home --config /config/config.yaml encrypt-secrets
voice-home --config /config/config.yaml validate
```

Danach können YAML und Schlüssel read-only eingebunden werden, solange keine
neuen Klartextwerte vorliegen. `validate` verschlüsselt nicht und schreibt keine
temporäre Klartext-YAML. Nach manueller Klartexteingabe `encrypt-secrets` oder
den Dienst mit beschreibbarem Mount starten. Bei einem Schreibfehler wird der
Start abgebrochen, statt den Schutz still zu überspringen.

Ältere Images ohne diese Funktion verstehen `enc:v1:` nicht. Ein Downgrade
benötigt deshalb die vorherige, geschützt aufbewahrte Konfiguration bzw. neu
eingetragene Zugangsdaten; ein reiner Image-Rollback reicht nach der Migration
nicht aus. Keine produktiven Tür-/Toraktionen für Upgrade-Tests auslösen.
