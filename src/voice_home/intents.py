"""Exact full-utterance matching, never substring or fuzzy command execution."""

import re
from .config import Action


def normalize(text: str) -> str:
    text = text.casefold().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text).split())


class Intents:
    def __init__(self, actions: list[Action]):
        self.phrases: dict[str, str] = {}
        for action in actions:
            for alias in action.aliases:
                for pattern in action.patterns:
                    phrase = normalize(pattern.replace("{target}", alias))
                    # Articles are explicit in patterns; do not remove other words.
                    variants = {phrase}
                    tokens = phrase.split()
                    for i in range(len(tokens) + 1):
                        variants.add(" ".join(tokens[:i] + ["bitte"] + tokens[i:]))
                    for variant in variants:
                        if variant in self.phrases and self.phrases[variant] != action.id:
                            raise ValueError(f"Mehrdeutiges Sprachmuster: {variant}")
                        if variant in {"ja", "nein", "auflegen", "abbrechen", "tschüss", "tschuess"}:
                            raise ValueError("Sprachmuster kollidiert mit Dialogwort")
                        self.phrases[variant] = action.id

    def parse(self, text: str) -> tuple[str, str | None]:
        text = normalize(text)
        if text in {"nein", "nein danke", "auflegen", "bitte auflegen", "abbrechen", "tschuess"}:
            return "stop", None
        if text in {"ja", "ja bitte"}:
            return "yes", None
        if any(w in text.split() for w in {"nicht", "kein", "keine", "keinen", "niemals", "nein", "unk"}):
            return "unknown", None
        action = self.phrases.get(text)
        return ("action", action) if action else ("unknown", None)
