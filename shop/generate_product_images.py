#!/usr/bin/env python3
"""Generate realistic product photos via Vertex AI Imagen 3 API."""
import base64
import json
import os
import subprocess
import sys
import time

OUTPUT_DIR = "server/static/img/products"

PRODUCTS = [
    {"sku": "DRN-001", "name": "Skydio X10", "prompt": "Professional product photo of a Skydio X10 enterprise drone, quadcopter with obstacle avoidance sensors, matte grey body, on white background, studio lighting, 4K"},
    {"sku": "DRN-002", "name": "Parrot ANAFI Ai", "prompt": "Professional product photo of a Parrot ANAFI Ai drone, compact foldable white quadcopter with 4G connectivity, on white background, studio lighting, 4K"},
    {"sku": "DRN-003", "name": "Autel EVO II Pro V3", "prompt": "Professional product photo of Autel EVO II Pro V3 drone, orange and grey foldable quadcopter with camera gimbal, on white background, studio lighting, 4K"},
    {"sku": "DRN-004", "name": "Wingtra WingtraOne GEN II", "prompt": "Professional product photo of a Wingtra WingtraOne GEN II fixed-wing VTOL survey drone, white delta wing aircraft, on white background, studio lighting, 4K"},
    {"sku": "DRN-005", "name": "Quantum-Systems Trinity F90+", "prompt": "Professional product photo of Quantum-Systems Trinity F90+ fixed-wing VTOL survey drone, white and blue sleek design, on white background, studio lighting, 4K"},
    {"sku": "DRN-006", "name": "Flyability ELIOS 3", "prompt": "Professional product photo of Flyability ELIOS 3 indoor inspection drone inside protective cage/sphere, compact drone in spherical cage guard, on white background, studio lighting, 4K"},
    {"sku": "DRN-007", "name": "Parrot ANAFI USA", "prompt": "Professional product photo of Parrot ANAFI USA military-grade compact foldable drone, dark grey tactical quadcopter, on white background, studio lighting, 4K"},
    {"sku": "DRN-008", "name": "Freefly Astro", "prompt": "Professional product photo of Freefly Astro enterprise mapping drone, black industrial quadcopter with large propellers, on white background, studio lighting, 4K"},
    {"sku": "FRM-001", "name": "Holybro X500 V2 Frame Kit", "prompt": "Professional product photo of a Holybro X500 V2 drone frame kit, carbon fiber quadcopter frame with arms and mounting plates, on white background, studio lighting, 4K"},
    {"sku": "FRM-002", "name": "IFlight Chimera7 Pro Frame", "prompt": "Professional product photo of IFlight Chimera7 Pro FPV racing drone frame, carbon fiber long-range frame with 7-inch prop guards, on white background, studio lighting, 4K"},
    {"sku": "MOT-001", "name": "KDE Direct 4215XF-465 Motor", "prompt": "Professional product photo of a KDE Direct brushless drone motor, silver and black cylindrical motor with exposed windings, on white background, studio lighting, 4K"},
    {"sku": "ESC-001", "name": "Holybro Tekko32 F4 4-in-1 ESC", "prompt": "Professional product photo of Holybro Tekko32 F4 4-in-1 ESC electronic speed controller circuit board, green PCB with components and connectors, on white background, studio lighting, 4K"},
    {"sku": "FLC-001", "name": "Holybro Pixhawk 6X", "prompt": "Professional product photo of Holybro Pixhawk 6X flight controller module, small black electronics module with connectors and ports, on white background, studio lighting, 4K"},
    {"sku": "FLC-002", "name": "CUAV X7+ Pro", "prompt": "Professional product photo of CUAV X7+ Pro flight controller, small black and orange electronics module with cable connectors, on white background, studio lighting, 4K"},
    {"sku": "GMB-001", "name": "Freefly MoVI Carbon Gimbal", "prompt": "Professional product photo of Freefly MoVI Carbon camera gimbal stabilizer for drones, black carbon fiber 3-axis gimbal mount, on white background, studio lighting, 4K"},
    {"sku": "CAM-001", "name": "Phase One P3 Payload", "prompt": "Professional product photo of Phase One P3 aerial camera payload, professional medium format camera module for drone mapping, on white background, studio lighting, 4K"},
    {"sku": "BAT-001", "name": "Tattu 6S 10000mAh LiPo", "prompt": "Professional product photo of a Tattu 6S 10000mAh LiPo battery pack, large rectangular blue and black battery with XT90 connector, on white background, studio lighting, 4K"},
    {"sku": "BAT-002", "name": "EcoFlow DELTA Mini", "prompt": "Professional product photo of EcoFlow DELTA Mini portable power station, compact grey and black rectangular power unit with display and ports, on white background, studio lighting, 4K"},
    {"sku": "PRP-001", "name": "KDE Direct CF 15.5x5.3 Props", "prompt": "Professional product photo of a pair of KDE Direct carbon fiber drone propellers, black carbon fiber props with brass hub, on white background, studio lighting, 4K"},
    {"sku": "PRP-002", "name": "Master Airscrew 13x4.5 Silent Props", "prompt": "Professional product photo of a set of 4 Master Airscrew silent drone propellers, translucent grey plastic propellers, on white background, studio lighting, 4K"},
    {"sku": "FPV-001", "name": "Orqa FPV.One Pilot Goggles", "prompt": "Professional product photo of Orqa FPV.One pilot goggles, sleek white FPV headset with dual screens and adjustable headband, on white background, studio lighting, 4K"},
    {"sku": "FPV-002", "name": "TBS Crossfire Nano TX", "prompt": "Professional product photo of TBS Crossfire Nano TX module, tiny black long-range radio transmitter module with antenna connector, on white background, studio lighting, 4K"},
    {"sku": "ACC-001", "name": "Hoodman Drone Launch Pad", "prompt": "Professional product photo of a Hoodman 5-foot drone launch pad, large circular orange and black landing pad with OCTO logo, flat lay top view, on white background, studio lighting, 4K"},
    {"sku": "ACC-002", "name": "Lowepro DroneGuard BP 450 AW", "prompt": "Professional product photo of Lowepro DroneGuard BP 450 AW drone backpack, black professional camera/drone carrying backpack with compartments visible, on white background, studio lighting, 4K"},
]

PROJECT = "emea-461114"
LOCATION = "us-central1"
MODEL = "imagen-3.0-generate-002"


def get_access_token():
    result = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def generate_image(prompt, output_path, token):
    """Generate a single product image using Vertex AI Imagen 3."""
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/{MODEL}:predict"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "1:1",
            "outputOptions": {"mimeType": "image/png"},
        },
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
    if "predictions" not in data:
        return False, f"No predictions in response: {str(data)[:200]}"

    img_b64 = data["predictions"][0].get("bytesBase64Encoded", "")
    if not img_b64:
        return False, "No image data in prediction"

    img_bytes = base64.b64decode(img_b64)
    with open(output_path, "wb") as f:
        f.write(img_bytes)
    return True, f"{len(img_bytes)} bytes"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    token = get_access_token()
    if not token:
        print("ERROR: Could not get access token")
        sys.exit(1)

    results = []
    for i, product in enumerate(PRODUCTS):
        sku = product["sku"].lower().replace("-", "_")
        output_path = os.path.join(OUTPUT_DIR, f"{sku}.png")

        # Skip if already generated
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            print(f"[{i+1}/{len(PRODUCTS)}] SKIP {product['name']} (already exists)")
            results.append({"sku": product["sku"], "status": "skipped"})
            continue

        print(f"[{i+1}/{len(PRODUCTS)}] Generating {product['name']}...", end=" ", flush=True)
        success, msg = generate_image(product["prompt"], output_path, token)
        if success:
            print(f"OK ({msg})")
            results.append({"sku": product["sku"], "status": "ok", "file": output_path})
        else:
            print(f"FAIL: {msg}")
            results.append({"sku": product["sku"], "status": "fail", "error": msg})

        # Small delay to avoid rate limiting
        time.sleep(1)

    ok = sum(1 for r in results if r["status"] in ("ok", "skipped"))
    fail = sum(1 for r in results if r["status"] == "fail")
    print(f"\nDone: {ok} ok, {fail} failed out of {len(PRODUCTS)}")


if __name__ == "__main__":
    main()
