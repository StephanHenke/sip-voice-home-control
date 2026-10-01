import argparse
import json

import httpx
import yaml

from .config import load, credential
from .runtime import read_status
from .settings import SettingsError
from .logging_config import configure, suppress_native_output
from .dialog import Dialog


def main():
    parser = argparse.ArgumentParser(description="Lokaler SIP-Sprachcontroller")
    parser.add_argument("--config", default="/config/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Konfiguration prüfen, keine Verbindungen")
    sub.add_parser("doctor", help="openHAB lesend prüfen, keine Befehle senden")
    sub.add_parser("serve", help="SIP und Sprachdialog starten")
    sub.add_parser("web", help="HTTPS-Administration und Controller starten")
    sub.add_parser("web-password", help="Admin-Passwort interaktiv zurücksetzen")
    probe = sub.add_parser("register", help="Nur SIP-Anmeldung testen; alle Anrufe ablehnen")
    probe.add_argument("--seconds", type=float, default=15)
    sub.add_parser("status", help="Aktuellen Betriebszustand als JSON ausgeben")
    sub.add_parser("health", help="Aktuellen lokalen Healthcheck auswerten")
    parse = sub.add_parser("parse", help="Sprachtext offline zuordnen")
    parse.add_argument("text")
    args = parser.parse_args()
    try:
        if args.command == 'web-password':
            from .web import reset_password
            reset_password()
            return
        if args.command == 'web':
            from .web import serve
            serve(args.config)
            return
        config = load(args.config)
        if args.command in {'serve', 'register'}:
            suppress_native_output()
        if args.command in {'serve', 'register', 'doctor'}:
            values = []
            if args.command != 'doctor':
                values.append(credential(config.sip, 'password'))
            if args.command != 'register':
                values.append(credential(config.openhab, 'token'))
            configure(config.logging, values)
        dialog = Dialog(config)
        if args.command == "validate":
            print(json.dumps({"valid": True, "callers": len(config.callers), "actions": len(config.actions), "phrases": len(dialog.intents.phrases)}))
        elif args.command == "parse":
            print(json.dumps(dialog.intents.parse(args.text), ensure_ascii=False))
        elif args.command == "doctor":
            from .smarthome import create_adapter
            client = create_adapter(config)
            try:
                print(json.dumps(client.check(config.actions, config.call_control)))
            finally:
                client.close()
        elif args.command in {'health', 'status'}:
            status = read_status()
            if args.command == 'status':
                print(json.dumps(status))
                raise SystemExit(0 if status['fresh'] else 1)
            raise SystemExit(0 if status['fresh'] and status.get('registered') and status.get('speech_ready') else 1)
        else:
            from .sip import Engine
            engine = Engine(config, probe=args.command == "register")
            ok = engine.run(args.seconds if args.command == "register" else None)
            if args.command == "register":
                print(json.dumps({"registration_success": ok}))
                raise SystemExit(0 if ok else 1)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, yaml.YAMLError, httpx.HTTPError) as exc:
        # Do not dump entire configurations or secret values in exception output.
        import sys
        detail = str(exc) if isinstance(exc, SettingsError) else type(exc).__name__
        print(f"Konfiguration/Datei nicht verwendbar ({detail})", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
