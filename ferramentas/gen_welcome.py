import os
import urllib.request
import json

k = os.environ.get("ELEVENLABS_API_KEY")
if not k:
    raise SystemExit("defina ELEVENLABS_API_KEY no ambiente")
url = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io") + "/v1/text-to-speech/" + os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
headers = {
    'xi-api-key': k,
    'Content-Type': 'application/json'
}
payload = json.dumps({
    'text': 'Identidade confirmada. Bem-vindo de volta, Senhor Werik. Todos os sistemas online e à sua disposição.',
    'model_id': 'eleven_multilingual_v2',
    'voice_settings': {
        'stability': 0.55,
        'similarity_boost': 0.85,
        'style': 0.15,
        'use_speaker_boost': True
    }
}).encode('utf-8')

req = urllib.request.Request(url, data=payload, headers=headers)
with urllib.request.urlopen(req, timeout=15) as resp:
    data = resp.read()
    with open('c:/JARVIS/welcome_werik.mp3', 'wb') as f:
        f.write(data)
    print(f"Generated welcome_werik.mp3 with ElevenLabs George: {len(data)} bytes")
