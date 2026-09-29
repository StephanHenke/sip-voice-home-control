"""Offline speech with optional command vocabulary and an unrestricted guard."""

import hashlib
import json
import math
from pathlib import Path
import re
import struct
import wave

from .intents import Intents, STOP_PHRASES, YES_PHRASES, normalize


NEGATIONS = {"nicht", "nie", "niemals", "kein", "keine", "keinen", "keiner", "keinem", "keines", "nein", "nee", "noe", "ohne"}
# Keep refusals, opposite commands and ordinary sentence context recognizable.
CONTEXT_WORDS = "ja bitte nein danke nee nö abbrechen auflegen tschüss nicht nie niemals kein keine keinen keiner keinem keines ohne auf keinen fall öffnen öffne schließen schließe offen geschlossen zu auf an aus einschalten ausschalten ich du wir er sie es das die der ein eine ist sind war wird wurde schon noch jetzt später morgen vielleicht wenn kann kannst könnte soll sollst sollte möchte will wollte aber und oder nur".split()


def command_vocabulary(actions) -> list[str]:
    words = set(CONTEXT_WORDS) | {"[unk]"}
    for action in actions:
        for alias in action.aliases:
            for pattern in action.patterns:
                words.update(re.findall(r"\w+", pattern.replace("{target}", alias).lower()))
    # Individual words preserve arbitrary order and extra words for exact parsing.
    return sorted(words)


class Speech:
    def __init__(self, config: dict, cache: Path, prompts: set[str], actions=()):
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from vosk import Model, SetLogLevel
        from piper import PiperVoice
        SetLogLevel(-1)
        self.config, self.cache = config, cache
        cache.mkdir(parents=True, exist_ok=True)
        self.model = Model(config["asr_model"])
        self.recognizer = None
        self.guard = None
        self.intents = Intents(actions)
        self.vocabulary = command_vocabulary(actions) if actions and config.get("command_vocabulary", True) else None
        voice_path = Path(config["tts_model"])
        # Invalidate cached WAVs on voice model/config changes.
        self.voice_key = hashlib.sha256(voice_path.read_bytes() + Path(str(voice_path) + ".json").read_bytes()).hexdigest()
        missing = [p for p in prompts if not self.path(p).exists()]
        if missing:
            voice = PiperVoice.load(str(voice_path), use_cuda=False)
            for text in sorted(missing):
                temporary = self.path(text).with_suffix(".tmp.wav")
                with wave.open(str(temporary), "wb") as output:
                    voice.synthesize_wav(text, output)
                temporary.replace(self.path(text))
        self.beep = cache / "ready.wav"
        with wave.open(str(self.beep), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(b"".join(struct.pack("<h", int(2200 * math.sin(2 * math.pi * 700 * i / 16000))) for i in range(1280)))

    def path(self, text: str) -> Path:
        digest = hashlib.sha256((self.voice_key + text).encode()).hexdigest()
        return self.cache / f"{digest}.wav"

    def reset(self):
        from vosk import KaldiRecognizer
        if self.vocabulary:
            self.recognizer = KaldiRecognizer(self.model, 16000, json.dumps(self.vocabulary, ensure_ascii=False))
            self.guard = KaldiRecognizer(self.model, 16000)
            self.guard.SetWords(True)
        else:
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.guard = None
        self.recognizer.SetWords(True)

    def feed(self, pcm: bytes) -> tuple[str, float] | None:
        endpoint = self.recognizer.AcceptWaveform(pcm)
        if self.guard:
            self.guard.AcceptWaveform(pcm)
        if endpoint:
            return self._select(self.recognizer.Result(), self.guard.Result() if self.guard else None, self.intents)
        return None

    def finish(self) -> tuple[str, float] | None:
        return self._select(self.recognizer.FinalResult(), self.guard.FinalResult() if self.guard else None, self.intents)

    @classmethod
    def _select(cls, raw: str, guard_raw: str | None, intents=None) -> tuple[str, float] | None:
        result = cls._result(raw)
        if guard_raw is None or result is None:
            return result
        guard = cls._result(guard_raw)
        if guard is None:
            return None  # A vocabulary-only guess over noise is not a command.
        text, confidence = result
        normalized = normalize(text)
        guard_text = normalize(guard[0])
        # An unrestricted refusal must never turn into a positive command.
        if set(guard_text.split()) & NEGATIONS or guard_text in STOP_PHRASES:
            return guard
        # Confirmation requires agreement from the unrestricted decoder as well.
        if normalized in YES_PHRASES:
            return (text, min(confidence, guard[1])) if guard_text in YES_PHRASES else (text, 0.0)
        if guard_text in YES_PHRASES:
            return guard  # A plain Yes cannot become an opening command.
        if normalized in STOP_PHRASES:
            return text, 0.0
        if intents is not None:
            candidate = intents.parse(text)
            unrestricted = intents.parse(guard[0])
            if candidate[0] == unrestricted[0] == "action" and candidate != unrestricted:
                return text, 0.0  # Conflicting known targets must be clarified.
        return result

    @staticmethod
    def _result(raw: str) -> tuple[str, float] | None:
        result = json.loads(raw)
        if not result.get("text"):
            return None
        confidences = [w.get("conf", 0) for w in result.get("result", [])]
        return result["text"], min(confidences, default=0)
