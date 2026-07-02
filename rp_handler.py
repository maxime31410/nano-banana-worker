import runpod
import json
import urllib.request
import time
import os
import requests
import base64
import uuid

COMFY_HOST = "127.0.0.1:8188"
COMFY_INPUT_DIR = "/comfyui/input"
COMFY_OUTPUT_DIR = "/comfyui/output"
TIMEOUT = 840  # 14 min max par job


def wait_for_service():
    while True:
        try:
            requests.get(f"http://{COMFY_HOST}/system_stats", timeout=5)
            print("ComfyUI API is ready")
            return
        except Exception:
            print("Waiting for ComfyUI...")
            time.sleep(1)


def upload_file(filename, data_bytes):
    os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
    with open(os.path.join(COMFY_INPUT_DIR, filename), "wb") as f:
        f.write(data_bytes)
    print(f"Uploaded file: {filename}")


def queue_prompt(workflow, client_id):
    payload = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=payload)
    response = json.loads(urllib.request.urlopen(req).read())
    return response["prompt_id"]


def get_history(prompt_id):
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as r:
        return json.loads(r.read())


def wait_for_completion(prompt_id):
    """Poll /history until the prompt appears (= finished or errored)."""
    start = time.time()
    while time.time() - start < TIMEOUT:
        history = get_history(prompt_id)
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = json.dumps(status.get("messages", []))[:800]
                raise Exception(f"Workflow error: {msgs}")
            return entry
        time.sleep(3)
    raise Exception(f"Timeout: workflow not finished after {TIMEOUT}s")


MEDIA_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".gif": "image/gif",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".flac": "audio/flac",
}


def collect_outputs(entry):
    """Scan every output node for any file reference (gifs, images, videos, audio...)."""
    outputs = []
    for node_id, node_output in entry.get("outputs", {}).items():
        for key, value in node_output.items():
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                filename = item["filename"]
                subfolder = item.get("subfolder", "")
                filepath = os.path.join(COMFY_OUTPUT_DIR, subfolder, filename)
                if not os.path.exists(filepath):
                    continue
                with open(filepath, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                ext = os.path.splitext(filename)[1].lower()
                outputs.append({
                    "filename": filename,
                    "type": "base64",
                    "data": data,
                    "media_type": MEDIA_TYPES.get(ext, "application/octet-stream"),
                })
    return outputs


def handler(job):
    job_input = job["input"]
    workflow = job_input.get("workflow")
    if not workflow:
        return {"error": "No workflow provided"}

    for img in job_input.get("images", []):
        data = img["image"]
        if "," in data:
            data = data.split(",", 1)[1]
        upload_file(img["name"], base64.b64decode(data))

    for audio in job_input.get("audio", []):
        data = audio["audio"]
        if "," in data:
            data = data.split(",", 1)[1]
        upload_file(audio["name"], base64.b64decode(data))

    client_id = str(uuid.uuid4())

    try:
        prompt_id = queue_prompt(workflow, client_id)
        print(f"Queued workflow: {prompt_id}")
    except Exception as e:
        return {"error": f"Failed to queue workflow: {str(e)}"}

    try:
        entry = wait_for_completion(prompt_id)
        outputs = collect_outputs(entry)
    except Exception as e:
        return {"error": f"Workflow execution failed: {str(e)}"}

    if not outputs:
        return {"error": "Workflow produced no output files"}

    return {"files": outputs}


if __name__ == "__main__":
    wait_for_service()
    print("Starting RunPod handler...")
    runpod.serverless.start({"handler": handler})
