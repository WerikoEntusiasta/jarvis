import urllib.request
import json

k=os.environ.get("ELEVENLABS_API_KEY")
req = urllib.request.Request('https://api.elevenlabs.io/v1/voices', headers={'xi-api-key': k})
with urllib.request.urlopen(req) as resp:
    voices = json.loads(resp.read().decode('utf-8'))['voices']
    for v in voices:
        print(f"{v['name']} | ID: {v['voice_id']} | Category: {v.get('category')}")
