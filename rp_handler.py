import runpod
import json
import urllib.request
import time
import os
import requests
import base64
import uuid
import boto3
from botocore.config import Config

COMFY_HOST = "127.0.0.1:8188"
COMFY_INPUT_DIR = "/comfyui/input"
COMFY_OUTPUT_DIR = "/comfyui/output"
TIMEOUT = 3600  # 60 min max par job (marge large pour 3+ clips, upscale, RIFE)


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


def get_s3_client():
    endpoint_url = os.environ.get("BUCKET_ENDPOINT_URL")
    access_key = os.environ.get("BUCKET_ACCESS_KEY_ID")
    secret_key = os.environ.get("BUCKET_SECRET_ACCESS_KEY")
    if not all([endpoint_url, access_key, secret_key]):
        return None, None
    # BUCKET_ENDPOINT_URL is expected as https://<account_id>.r2.cloudflarestorage.com/<bucket>
    base_endpoint, _, bucket_name = endpoint_url.rstrip("/").rpartition("/")
    client = boto3.client(
        "s3",
        endpoint_url=base_endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",  # required convention for Cloudflare R2
        config=Config(signature_version="s3v4"),
    )
    return client, bucket_name


def collect_outputs(entry, job_id):
    """Scan every output node for any file reference (gifs, images, videos, audio...)
    and upload each one to R2, returning URLs instead of embedding base64 data
    (avoids RunPod's response payload size limit)."""
    s3_client, bucket_name = get_s3_client()
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
                ext = os.path.splitext(filename)[1].lower()
                media_type = MEDIA_TYPES.get(ext, "application/octet-stream")

                if s3_client:
                    object_key = f"{job_id}/{filename}"
                    s3_client.upload_file(
                        filepath, bucket_name, object_key,
                        ExtraArgs={"ContentType": media_type},
                    )
                    url = s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket_name, "Key": object_key},
                        ExpiresIn=604800,  # 7 days
                    )
                    outputs.append({"filename": filename, "type": "url", "url": url, "media_type": media_type})
                else:
                    # Fallback: no bucket configured, embed as base64 (small files only)
                    with open(filepath, "rb") as f:
                        data = base64.b64encode(f.read()).decode("utf-8")
                    outputs.append({
                        "filename": filename, "type": "base64", "data": data, "media_type": media_type,
                    })
    return outputs


def patch_media_inputs(workflow, uploaded_images, uploaded_audio):
    """Overwrite LoadImage/LoadAudio nodes in the workflow with the filenames
    actually uploaded for this job, so the workflow JSON itself never needs
    to be edited by hand between requests."""
    image_name = uploaded_images[0]["name"] if uploaded_images else None
    audio_name = uploaded_audio[0]["name"] if uploaded_audio else None

    for node in workflow.values():
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        if class_type == "LoadImage" and image_name:
            inputs["image"] = image_name
        elif class_type == "LoadAudio" and audio_name:
            inputs["audio"] = audio_name
            if "audioUI" in inputs:
                inputs["audioUI"] = f"/api/view?filename={audio_name}&type=input&subfolder="
    return workflow


def handler(job):
    job_input = job["input"]
    workflow = job_input.get("workflow")
    if not workflow:
        return {"error": "No workflow provided"}

    uploaded_images = job_input.get("images", [])
    uploaded_audio = job_input.get("audio", [])

    for img in uploaded_images:
        data = img["image"]
        if "," in data:
            data = data.split(",", 1)[1]
        upload_file(img["name"], base64.b64decode(data))

    for audio in uploaded_audio:
        data = audio["audio"]
        if "," in data:
            data = data.split(",", 1)[1]
        upload_file(audio["name"], base64.b64decode(data))

    workflow = patch_media_inputs(workflow, uploaded_images, uploaded_audio)

    client_id = str(uuid.uuid4())

    try:
        prompt_id = queue_prompt(workflow, client_id)
        print(f"Queued workflow: {prompt_id}")
    except Exception as e:
        return {"error": f"Failed to queue workflow: {str(e)}"}

    try:
        entry = wait_for_completion(prompt_id)
        outputs = collect_outputs(entry, job.get("id", client_id))
    except Exception as e:
        return {"error": f"Workflow execution failed: {str(e)}"}

    if not outputs:
        return {"error": "Workflow produced no output files"}

    return {"files": outputs}


if __name__ == "__main__":
    wait_for_service()
    print("Starting RunPod handler...")
    runpod.serverless.start({"handler": handler})
