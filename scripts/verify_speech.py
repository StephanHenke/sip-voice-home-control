"""Native CPU ASR regression check; synthetic speech, no SIP or device commands."""
import audioop
import json
from pathlib import Path
import tempfile
import time
import wave
from voice_home.config import load
from voice_home.intents import Intents
from voice_home.speech import Speech

phrases = {
    'Haustür öffnen.': 'action', 'Tür öffnen.': 'action', 'Öffne die Haustür.': 'action',
    'Garagentor öffnen.': 'action', 'Ja.': 'yes', 'Nein.': 'stop',
    'Haustür nicht öffnen.': 'unknown', 'Nicht die Tür öffnen.': 'unknown',
    'Öffne die Haustür nicht.': 'unknown', 'Die Haustür bleibt zu.': 'unknown',
    'Garagentor schließen.': 'unknown', 'Die Tür ist schon offen.': 'unknown',
    'Ich habe Haustür öffnen gesagt.': 'unknown', 'Öffne das Fenster.': 'unknown',
    'Haustür öffnen und Garage öffnen.': 'unknown', 'Nein, nicht öffnen.': 'unknown',
    'Vielleicht morgen die Haustür öffnen.': 'unknown', 'Was gibt es zum Mittagessen?': 'unknown',
    'Auf Wiedersehen.': 'unknown', 'Abbrechen.': 'stop',
}
targets = {'Haustür öffnen.': 'front_door_open', 'Tür öffnen.': 'front_door_open',
           'Öffne die Haustür.': 'front_door_open', 'Garagentor öffnen.': 'garage_open'}
config = load(Path(__file__).parents[1] / 'config.example.yaml')
parser = Intents(config.actions)
failures = []
with tempfile.TemporaryDirectory() as folder:
    speech = Speech(config.speech, Path(folder), set(phrases), config.actions)
    sources = []
    for phrase, expected in phrases.items():
        with wave.open(str(speech.path(phrase)), 'rb') as wav:
            pcm, _ = audioop.ratecv(wav.readframes(wav.getnframes()), 2, 1, wav.getframerate(), 16000, None)
        sources.append((phrase, pcm + b'\x00' * 32000, expected))
    sources.append(('silence', b'\x00' * 64000, 'unknown'))
    with wave.open(str(speech.beep), 'rb') as wav:
        sources.append(('beep', wav.readframes(wav.getnframes()) + b'\x00' * 64000, 'unknown'))
    for label, pcm, expected in sources:
        start = time.monotonic()
        speech.reset()
        recognized = None
        for i in range(0, len(pcm), 640):
            recognized = speech.feed(pcm[i:i+640])
            if recognized:
                break
        recognized = recognized or speech.finish()
        kind, target = parser.parse(recognized[0]) if recognized and recognized[1] >= config.speech['min_confidence'] else ('unknown', None)
        row = {'source': label, 'recognized': recognized, 'kind': kind, 'target': target, 'expected': expected, 'seconds': round(time.monotonic()-start, 3)}
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if kind != expected or target != targets.get(label):
            failures.append(label)
assert not failures, failures
