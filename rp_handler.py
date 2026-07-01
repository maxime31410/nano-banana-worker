import runpod
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
import uuid
import websocket

# ComfyUI server settings
COMFY_HOST = "127.0.0.1:8188"
COMFY_INPUT_DIR = "/comfyui/input"
COMFY_OUTPUT_DIR = "/comfyui/output"
TIMEOUT = 600  # 10 minutes max


def wait_for_service():
    """Wait until ComfyUI API is ready."""
    while True:
        try:
            requests.get(f"http://{COMFY_HOST}/system_stats", timeout=5)
            print("ComfyUI API is ready")
            return
        except Exception:
            print("Waiting for ComfyUI...")
            time.sleep(1)


def upload_file(filename, data_bytes):
    """Upload a file (image or audio) to ComfyUI input directory."""
    os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
    filepath = os.path.join(COMFY_INPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(data_bytes)
    print(f"Uploaded file: {filename}")


def queue_prompt(workflow, client_id):
    """Submit workflow to ComfyUI queue."""
    payload = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=payload)
    response = json.loads(urllib.request.urlopen(req).read())
    return response["prompt_id"]


def get_history(prompt_id):
    """Get execution history for a prompt."""
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as response:
        return json.loads(response.read())


def get_output_files(prompt_id):
    """Wait for workflow to complete and return output files as base64."""
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFY_HOST}/ws?clientId={prompt_id}")

    try:
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break  # Execution complete
    finally:
        ws.close()

    history = get_history(prompt_id)
    outputs = []

    if prompt_id not in history:
        return outputs

    for node_id, node_output in history[prompt_id]["outputs"].items():
        # Handle video/gif outputs
        if "gifs" in node_output:
            for gif in node_output["gifs"]:
                filename = gif["filename"]
                subfolder = gif.get("subfolder", "")
                filepath = os.path.join(COMFY_OUTPUT_DIR, subfolder, filename)
                if os.path.exists(filepath):
                    with open(filepath, "rb") as f:
                        file_data = base64.b64encode(f.read()).decode("utf-8")
                    outputs.append({
                        "filename": filename,
                        "type": "base64",
                        "data": file_data,
                        "media_type": "video/mp4" if filename.endswith(".mp4") else "image/gif"
                    })
        # Handle image outputs
        if "images" in node_output:
            for image in node_output["images"]:
                filename = image["filename"]
                subfolder = image.get("subfolder", "")
                filepath = os.path.join(COMFY_OUTPUT_DIR, subfolder, filename)
                if os.path.exists(filepath):
                    with open(filepath, "rb") as f:
                        file_data = base64.b64encode(f.read()).decode("utf-8")
                    outputs.append({
                        "filename": filename,
                        "type": "base64",
                        "data": file_data,
                        "media_type": "image/png"
                    })

    return outputs


def handler(job):
    """Main RunPod handler."""
    job_input = job["input"]
    workflow = job_input.get("workflow")

    if not workflow:
        return {"error": "No workflow provided"}

    # Upload images if provided
    images = job_input.get("images", [])
    for img in images:
        name = img["name"]
        image_data = img["image"]
        # Strip data URI prefix if present
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        file_bytes = base64.b64decode(image_data)
        upload_file(name, file_bytes)

    # Upload audio files if provided
    audio_files = job_input.get("audio", [])
    for audio in audio_files:
        name = audio["name"]
        audio_data = audio["audio"]
        if "," in audio_data:
            audio_data = audio_data.split(",", 1)[1]
        file_bytes = base64.b64decode(audio_data)
        upload_file(name, file_bytes)

    # Generate unique client ID
    client_id = str(uuid.uuid4())

    # Queue the workflow
    try:
        prompt_id = queue_prompt(workflow, client_id)
        print(f"Queued workflow: {prompt_id}")
    except Exception as e:
        return {"error": f"Failed to queue workflow: {str(e)}"}

    # Wait for output
    try:
        outputs = get_output_files(prompt_id)
    except Exception as e:
        return {"error": f"Workflow execution failed: {str(e)}"}

    if not outputs:
        return {"error": "Workflow produced no output files"}

    return {"files": outputs}


if __name__ == "__main__":
    wait_for_service()
    print("Starting RunPod handler...")
    runpod.serverless.start({"handler": handler})
