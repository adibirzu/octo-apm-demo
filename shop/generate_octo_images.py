#!/usr/bin/env python3
"""Generate images for OCTO-branded products via Vertex AI Imagen 3."""
import base64
import json
import os
import subprocess
import time

OUTPUT_DIR = "server/static/img/products"

PRODUCTS = [
    {"sku": "OCTO-001", "name": "Phantom Racer X1", "prompt": "Professional product photo of a sleek FPV racing drone, compact black and neon green quadcopter with exposed carbon fiber arms and racing canopy, on white background, studio lighting, 4K"},
    {"sku": "OCTO-002", "name": "Vortex Pro FPV", "prompt": "Professional product photo of Vortex Pro FPV racing quadcopter, aggressive low-profile design with red and black carbon fiber frame and racing camera, on white background, studio lighting, 4K"},
    {"sku": "OCTO-003", "name": "Ignite Micro Racer", "prompt": "Professional product photo of a tiny micro FPV racing drone, ultra-compact whoop-style indoor racing quad with prop guards, on white background, studio lighting, 4K"},
    {"sku": "OCTO-004", "name": "SkyLens 4K Pro", "prompt": "Professional product photo of a camera drone with 4K gimbal camera, white and grey foldable quadcopter similar to consumer photography drone, on white background, studio lighting, 4K"},
    {"sku": "OCTO-005", "name": "AeroFold Mini", "prompt": "Professional product photo of a compact foldable mini camera drone, small grey foldable travel drone with camera, fits in palm of hand, on white background, studio lighting, 4K"},
    {"sku": "OCTO-006", "name": "CinemaFly Xtreme", "prompt": "Professional product photo of a professional cinema drone for filmmaking, large black hexacopter with retractable landing gear and camera gimbal mount, on white background, studio lighting, 4K"},
    {"sku": "OCTO-007", "name": "TerraSurvey RTK", "prompt": "Professional product photo of a survey and mapping drone with RTK GPS, white industrial quadcopter with large GPS antenna and mapping camera, on white background, studio lighting, 4K"},
    {"sku": "OCTO-008", "name": "InspectMaster Thermal", "prompt": "Professional product photo of an industrial inspection drone with thermal camera, dark grey quadcopter with dual visible and infrared camera payload, on white background, studio lighting, 4K"},
    {"sku": "OCTO-009", "name": "AgriSprayer Pro", "prompt": "Professional product photo of an agricultural sprayer drone, large hexacopter with spray tanks and nozzle arms for crop spraying, on white background, studio lighting, 4K"},
    {"sku": "OCTO-010", "name": "Extra Flight Battery Pack", "prompt": "Professional product photo of a drone LiPo battery pack, black and yellow high-capacity lithium polymer battery with XT60 connector and balance lead, on white background, studio lighting, 4K"},
    {"sku": "OCTO-011", "name": "Propeller Guard Set", "prompt": "Professional product photo of a set of drone propeller guards, four lightweight plastic prop guards in a row for quadcopter drone, on white background, studio lighting, 4K"},
    {"sku": "OCTO-012", "name": "Rugged Carrying Case", "prompt": "Professional product photo of a rugged drone carrying case, black hard-shell waterproof case with custom foam cutouts for drone and accessories visible inside, on white background, studio lighting, 4K"},
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
        fname = p["sku"].lower().replace("-", "_") + ".png"
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            print(f"[{i+1}/{len(PRODUCTS)}] SKIP {p['name']}")
            continue
        print(f"[{i+1}/{len(PRODUCTS)}] Generating {p['name']}...", end=" ", flush=True)
        ok, msg = generate_image(p["prompt"], path, token)
        print(f"{'OK' if ok else 'FAIL'}: {msg}")
        time.sleep(2)


if __name__ == "__main__":
    main()
