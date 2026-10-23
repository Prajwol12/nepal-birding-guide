import os
import re

from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not found. Check that .env is in this folder and contains GEMINI_API_KEY=...")

client = genai.Client(api_key=api_key)

try:
    models = []
    for m in client.models.list():
        if "generateContent" in (getattr(m, "supported_actions", None) or []):
            models.append(m.name.replace("models/", ""))
except Exception as e:
    raise SystemExit(f"Could not list models: {type(e).__name__}: {e}")

skip = ("image", "live", "tts", "audio", "lite", "robotics", "embedding")
flash = sorted(n for n in models if "flash" in n and not any(x in n for x in skip))
print(f"{len(models)} text-capable models. Those with 'flash' in the name:")
for n in flash:
    print("  ", n)


def version(name):
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return float(nums[0]) if nums else 0.0


stable = [n for n in flash if not any(x in n for x in ("preview", "exp", "latest"))]
pool = stable or flash
MODEL = os.getenv("GEMINI_MODEL") or (max(pool, key=version) if pool else None)
if not MODEL:
    raise SystemExit("No Flash model found in the list above. Paste this output to me.")
print("\nUsing model:", MODEL)

try:
    response = client.models.generate_content(
        model=MODEL,
        contents="In one sentence, what is a Himalayan Monal?",
    )
    print("\nAnswer:", response.text)
except Exception as e:
    print(f"\nRequest failed: {type(e).__name__}: {e}")
    print("A 429 error means the free quota is used up; wait a minute or check aistudio.google.com/rate-limit.")