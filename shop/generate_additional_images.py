#!/usr/bin/env python3
"""Generate images for ADDITIONAL_PRODUCTS via Vertex AI Imagen 3."""
import base64
import json
import os
import subprocess
import time

OUTPUT_DIR = "server/static/img/products"

PRODUCTS = [
    {"sku": "DRN-009", "name": "Teledyne FLIR SIRAS", "prompt": "Professional product photo of Teledyne FLIR SIRAS industrial inspection drone with thermal camera, dark grey quadcopter with dual sensor payload, on white background, studio lighting, 4K"},
    {"sku": "DRN-010", "name": "Inspired Flight IF800 TOMCAT", "prompt": "Professional product photo of Inspired Flight IF800 TOMCAT heavy-lift enterprise quadcopter, large black industrial drone with payload rails, on white background, studio lighting, 4K"},
    {"sku": "GMB-002", "name": "Gremsy T7 Gimbal", "prompt": "Professional product photo of Gremsy T7 3-axis camera gimbal stabilizer for drones, silver and black gimbal with camera mount, on white background, studio lighting, 4K"},
    {"sku": "BAT-003", "name": "Hitec X2 AC Plus Charger", "prompt": "Professional product photo of Hitec X2 AC Plus Black Edition dual-channel LiPo battery charger, black desktop charger with LCD display and banana plugs, on white background, studio lighting, 4K"},
    {"sku": "FLC-003", "name": "CubePilot Here4 GNSS", "prompt": "Professional product photo of CubePilot Here4 GNSS RTK module, small circular black GPS module with antenna dome, on white background, studio lighting, 4K"},
    {"sku": "FPV-003", "name": "Doodle Labs Smart Radio", "prompt": "Professional product photo of Doodle Labs Smart Radio mesh radio module for drones, small industrial radio transceiver with antenna connectors, on white background, studio lighting, 4K"},
    {"sku": "FRM-003", "name": "Foxtech Nimbus VTOL Airframe", "prompt": "Professional product photo of Foxtech Nimbus VTOL fixed-wing drone airframe, white composite VTOL aircraft with quad rotors on wings, on white background, studio lighting, 4K"},
    {"sku": "ACC-003", "name": "Tronair Payload Transit Case", "prompt": "Professional product photo of a rugged black hard transport case for drones, Pelican-style hard case with custom foam insert visible inside, on white background, studio lighting, 4K"},
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
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(img_b64))
    return True, f"{os.path.getsize(output_path)} bytes"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    token = get_access_token()
    for i, p in enumerate(PRODUCTS):
        sku = p["sku"].lower().replace("-", "_")
        path = os.path.join(OUTPUT_DIR, f"{sku}.png")
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            print(f"[{i+1}/{len(PRODUCTS)}] SKIP {p['name']}")
            continue
        print(f"[{i+1}/{len(PRODUCTS)}] Generating {p['name']}...", end=" ", flush=True)
        ok, msg = generate_image(p["prompt"], path, token)
        print(f"{'OK' if ok else 'FAIL'}: {msg}")
        time.sleep(2)  # Rate limit buffer


if __name__ == "__main__":
    main()
