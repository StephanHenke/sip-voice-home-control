import argparse
import json
import logging
import time

import httpx
import yaml

from .config import load
from .dialog import Dialog


def main():
    parser = argparse.ArgumentParser(description="Lokaler SIP-Sprachcontroller")
    parser.add_argument("--config", default="/config/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Konfiguration prüfen, keine Verbindungen")
    sub.add_parser("doctor", help="openHAB lesend prüfen, keine Befehle senden")
    sub.add_parser("serve", help="SIP und Sprachdialog starten")
    probe = sub.add_parser("register", help="Nur SIP-Anmeldung testen; alle Anrufe ablehnen")
    probe.add_argument("--seconds", type=float, default=15)
    sub.add_parser("health", help="Aktuellen lokalen Healthcheck auswerten")
    parse = sub.add_parser("parse", help="Sprachtext offline zuordnen")
    parse.add_argument("text")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load(args.config)
        dialog = Dialog(config)
        if args.command == "validate":
            print(json.dumps({"valid": True, "callers": len(config.callers), "actions": len(config.actions), "phrases": len(dialog.intents.phrases)}))
        elif args.command == "parse":
            print(json.dumps(dialog.intents.parse(args.text), ensure_ascii=False))
        elif args.command == "doctor":
            from .openhab import OpenHAB
            client = OpenHAB(config.openhab)
            try:
                print(json.dumps(client.check(config.actions)))
            finally:
                client.close()
        elif args.command == "health":
            status = json.loads((config.data_dir / "health.json").read_text())
            raise SystemExit(0 if time.time() - status["at"] < 15 and status["registered"] and status["speech_ready"] else 1)
        else:
            from .sip import Engine
            engine = Engine(config, probe=args.command == "register")
            ok = engine.run(args.seconds if args.command == "register" else None)
            if args.command == "register":
                print(json.dumps({"registration_success": ok}))
                raise SystemExit(0 if ok else 1)
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError, httpx.HTTPError) as exc:
        # Do not dump entire configurations or secret values in exception output.
        logging.error("Konfiguration/Datei nicht verwendbar (%s)", type(exc).__name__)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
