"""Offline speech; unrestricted transcription avoids forcing noise into commands."""

import hashlib
import json
import math
from pathlib import Path
import struct
import wave


class Speech:
    def __init__(self, config: dict, cache: Path, prompts: set[str]):
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from vosk import Model, SetLogLevel
        from piper import PiperVoice
        SetLogLevel(-1)
        self.config, self.cache = config, cache
        cache.mkdir(parents=True, exist_ok=True)
        self.model = Model(config["asr_model"])
        self.recognizer = None
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
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.recognizer.SetWords(True)

    def feed(self, pcm: bytes) -> tuple[str, float] | None:
        if self.recognizer.AcceptWaveform(pcm):
            return self._result(self.recognizer.Result())
        return None

    def finish(self) -> tuple[str, float] | None:
        return self._result(self.recognizer.FinalResult())

    @staticmethod
    def _result(raw: str) -> tuple[str, float] | None:
        result = json.loads(raw)
        if not result.get("text"):
            return None
        confidences = [w.get("conf", 0) for w in result.get("result", [])]
        return result["text"], min(confidences, default=0)
