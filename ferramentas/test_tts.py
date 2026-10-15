import os
import urllib.request
import json
import urllib.error

keys = [
    ('Key 1', os.environ.get("ELEVENLABS_API_KEY")),
    ('Key 2', os.environ.get("ELEVENLABS_API_KEY")),
]

for label, k in keys:
    url = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io") + "/v1/text-to-speech/" + os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    headers = {
        'xi-api-key': k,
        'Content-Type': 'application/json'
    }
    payload = json.dumps({
        'text': 'Identidade confirmada, Senhor Werik.',
        'model_id': 'eleven_multilingual_v2'
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            print(f"{label} SUCCESS! Audio bytes: {len(data)}")
            with open('c:/JARVIS/welcome_werik.mp3', 'wb') as f:
                f.write(data)
            break
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        print(f"{label} HTTP Error {e.code}: {body}")
    except Exception as e:
        print(f"{label} General Error: {e}")
