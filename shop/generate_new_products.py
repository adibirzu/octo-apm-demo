#!/usr/bin/env python3
"""Generate images for new products via Vertex AI Imagen 3."""
import base64
import json
import os
import subprocess
import time
from PIL import Image
import io

OUTPUT_DIR = "server/static/img/products"

PRODUCTS = [
    {"sku": "DRN-011", "name": "Aeronavics SkyJib-8", "prompt": "Professional product photo of a heavy-lift octocopter drone for cinema, black 8-motor drone with camera mount, on white background, studio lighting, 4K"},
    {"sku": "MOT-002", "name": "T-Motor U8 II KV100", "prompt": "Professional product photo of a T-Motor U8 II large brushless drone motor, black and silver high-torque motor with exposed copper windings, on white background, studio lighting, 4K"},
    {"sku": "CAM-002", "name": "Sony ILX-LR1 Aerial Camera", "prompt": "Professional product photo of Sony ILX-LR1 compact full-frame camera for drone mapping, small silver mirrorless camera body, on white background, studio lighting, 4K"},
    {"sku": "PRP-003", "name": "T-Motor G40x13 Folding Props (pair)", "prompt": "Professional product photo of large folding carbon fiber drone propellers, pair of black folding props with quick-release hub, on white background, studio lighting, 4K"},
    {"sku": "ACC-004", "name": "FLIR Vue TZ20-R Thermal Module", "prompt": "Professional product photo of FLIR Vue TZ20-R dual thermal camera module for drones, compact black thermal imaging sensor with dual lenses, on white background, studio lighting, 4K"},
    {"sku": "BAT-004", "name": "Tattu Plus 12S 22000mAh", "prompt": "Professional product photo of a large heavy-duty drone LiPo battery pack, chunky black and blue lithium polymer battery with XT90 connector, on white background, studio lighting, 4K"},
    {"sku": "FRM-004", "name": "DJI FlyCart 30 Frame Kit", "prompt": "Professional product photo of a large delivery drone frame, industrial hexacopter cargo drone frame with payload bay underneath, on white background, studio lighting, 4K"},
    {"sku": "ESC-002", "name": "Flame 80A HV ESC", "prompt": "Professional product photo of a high-voltage drone ESC speed controller, small black circuit board module with heavy gauge power wires, on white background, studio lighting, 4K"},
]

PROJECT = "emea-461114"
LOCATION = "us-central1"
MODEL = "imagen-3.0-generate-002"


def get_access_token():
    return subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True,
    ).stdout.strip()


def generate_image(prompt, output_path, token):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/{MODEL}:predict"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1", "outputOptions": {"mimeType": "image/png"}},
    }
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", url,
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(result.stdout)
    if "error" in data:
        return False, data["error"].get("message", str(data["error"]))
    img_b64 = data.get("predictions", [{}])[0].get("bytesBase64Encoded", "")
    if not img_b64:
        return False, "No image data"

    # Resize to 480x480 and save as JPG
    img = Image.open(io.BytesIO(base64.b64decode(img_b64)))
    img = img.resize((480, 480), Image.LANCZOS)
    img = img.convert("RGB")
    img.save(output_path, "JPEG", quality=85)
    return True, f"{os.path.getsize(output_path)} bytes"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    token = get_access_token()
    for i, p in enumerate(PRODUCTS):
        fname = p["sku"].lower().replace("-", "_") + ".jpg"
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            print(f"[{i+1}/{len(PRODUCTS)}] SKIP {p['name']}")
            continue
        print(f"[{i+1}/{len(PRODUCTS)}] Generating {p['name']}...", end=" ", flush=True)
        ok, msg = generate_image(p["prompt"], path, token)
        print(f"{'OK' if ok else 'FAIL'}: {msg}")
        time.sleep(2)


if __name__ == "__main__":
    main()
