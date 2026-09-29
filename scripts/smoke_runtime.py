"""Offline check of real TTS, ASR and PJSUA2 audio callbacks; no SIP/device traffic."""

import audioop
import json
from pathlib import Path
import queue
import tempfile
import time
from types import SimpleNamespace
import wave

import pjsua2 as pj

from voice_home.sip import AudioSink, Player
from voice_home.speech import Speech


def main():
    with tempfile.TemporaryDirectory() as directory:
        phrase = "Tür öffnen."
        speech = Speech({"asr_model": "/models/vosk-model-small-de-0.15", "tts_model": "/models/de_DE-thorsten-medium.onnx"}, Path(directory), {phrase})
        with wave.open(str(speech.path(phrase)), "rb") as wav:
            assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
            pcm, _ = audioop.ratecv(wav.readframes(wav.getnframes()), 2, 1, wav.getframerate(), 16000, None)
        speech.reset()
        recognized = speech.feed(pcm) or speech.finish()
        assert recognized and recognized[0], "ASR produced no transcription for synthesized speech"

        endpoint = pj.Endpoint()
        endpoint.libCreate()
        config = pj.EpConfig()
        config.uaConfig.threadCnt = 0
        config.uaConfig.mainThreadOnly = True
        config.logConfig.level = config.logConfig.consoleLevel = 1
        config.medConfig.clockRate = 16000
        endpoint.libInit(config)
        endpoint.libStart()
        endpoint.audDevManager().setNullDev()
        call = SimpleNamespace(listening=True, audio=queue.Queue(maxsize=500), audio_overflow=False, engine=SimpleNamespace(events=queue.Queue()))
        sink = AudioSink(call)
        player = Player(call, speech.path(phrase), "done")
        player.startTransmit(sink)
        deadline = time.monotonic() + 10
        received = []
        eof = False
        while time.monotonic() < deadline and not eof:
            endpoint.libHandleEvents(20)
            while not call.audio.empty():
                received.append(call.audio.get_nowait())
            while not call.engine.events.empty():
                event = call.engine.events.get_nowait()
                eof = event[0] == "playback"
                del event
        player.stopTransmit(sink)
        del player, sink
        endpoint.libDestroy()
        assert eof, "PJSUA2 did not deliver the playback-complete callback"
        assert any(frame and audioop.rms(frame, 2) > 100 for frame in received), "PJSUA2 did not deliver audible PCM"
        assert not call.audio_overflow
        print(json.dumps({"native_audio": "ok", "frames": len(received), "tts_asr_text": recognized[0]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
