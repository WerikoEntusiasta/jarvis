import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

import os

keys = [
    ("ELEVENLABS_API_KEY", os.environ.get("ELEVENLABS_API_KEY", "")),
    ("ELEVENLABS_FALLBACK_KEY", os.environ.get("ELEVENLABS_FALLBACK_KEY", ""))
]

for name, key in keys:
    print(f"\n=== ELEVENLABS ACCOUNT: {name} ===")
    try:
        req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key, "User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            voices = data.get("voices", [])
            print(f"Total voices: {len(voices)}")
            for v in voices:
                v_name = v.get("name", "")
                labels = v.get("labels", {})
                desc = f"{v.get('voice_id')} | {v_name} | {labels.get('accent', '')} {labels.get('description', '')} {labels.get('use_case', '')}"
                # Print all or relevant
                if any(k in str(v).lower() for k in ['jarvis', 'george', 'brian', 'daniel', 'adam', 'british', 'deep', 'butler']):
                    print(f"-> MATCH: {desc}")
    except Exception as e:
        print("Error:", e)
