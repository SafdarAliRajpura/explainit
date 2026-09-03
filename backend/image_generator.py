import os
import json
import requests
from urllib.parse import quote

STYLE_SUFFIX = ", premium digital comic book art, gorgeous stunning illustrations, vivid colors, rich cinematic lighting, masterpiece, highly detailed, expressive characters, distinct linework, 8k resolution, no blur, no text, no watermark"

with open("data/panel_script.json", "r") as f:
    script = json.load(f)

os.makedirs("data/images", exist_ok=True)

for panel in script["panels"]:
    panel_num = panel["panel_number"]
    prompt = panel["scene_description"] + STYLE_SUFFIX
    encoded_prompt = quote(prompt)

    print(f"Generating panel {panel_num}...")

    try:
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&model=flux&seed=42&nologo=true"
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        output_path = f"data/images/panel_{panel_num}.png"
        with open(output_path, "wb") as img_file:
            img_file.write(response.content)
        print(f"Saved: {output_path}\n")
    except Exception as e:
        print(f"FAILED on panel {panel_num}: {e}\n")

print("Done generating all panels.")