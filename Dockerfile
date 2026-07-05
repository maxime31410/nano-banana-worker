FROM runpod/worker-comfyui:5.8.5-base

# ── Mise à jour ComfyUI core (fix VAE audio LTX 2.3) ─────────────────────────
RUN cd /comfyui && git checkout master && git pull origin master
RUN pip install --upgrade comfy_aimdo || true
RUN cd /comfyui && pip install -r requirements.txt

# ── Tous les custom nodes via git clone ──────────────────────────────────────
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git && \
    git clone https://github.com/rgthree/rgthree-comfy.git && \
    git clone https://github.com/cubiq/ComfyUI_essentials.git && \
    git clone https://github.com/melMass/comfy_mtb.git && \
    git clone https://github.com/city96/ComfyUI-GGUF.git && \
    git clone https://github.com/yolain/ComfyUI-Easy-Use.git && \
    git clone https://github.com/ClownsharkBatwing/RES4LYF.git && \
    git clone https://github.com/kijai/ComfyUI-MelBandRoformer.git && \
    git clone https://github.com/Starnodes2024/ComfyUI_StarNodes.git && \
    git clone https://github.com/jomakaze/ComfyUI_JomaNodes.git && \
    git clone https://github.com/vslinx/comfyui-vslinx-nodes.git && \
    git clone https://github.com/Chaoses-Ib/ComfyUI_Ib_CustomNodes.git

# ── Fix : figer Frame-Interpolation à la version installée sur le pod ────
RUN cd /comfyui/custom_nodes/ComfyUI-Frame-Interpolation && \
    (git checkout v1.0.7 || git checkout $(git rev-list -n 1 --before="2025-07-01" HEAD)) && \
    echo "=== Frame-Interpolation pinné à ===" && git log -1 --format="%H %ci"

# ── Dépendances Python des nodes ─────────────────────────────────────────────
RUN cd /comfyui/custom_nodes/ComfyUI-Impact-Pack && pip install -r requirements.txt || true
RUN cd /comfyui/custom_nodes/ComfyUI-Frame-Interpolation && pip install -r requirements.txt || true
RUN cd /comfyui/custom_nodes/comfy_mtb && pip install -r requirements.txt || true
RUN cd /comfyui/custom_nodes/RES4LYF && pip install -r requirements.txt || true
RUN cd /comfyui/custom_nodes/ComfyUI-MelBandRoformer && pip install -r requirements.txt || true
RUN cd /comfyui/custom_nodes/ComfyUI_StarNodes && pip install -r requirements.txt || true

# ── Dépendances du handler custom ────────────────────────────────────────────
RUN pip install websocket-client runpod requests

# ── Handler personnalisé avec support audio ───────────────────────────────────
RUN printf "comfyui:\n    base_path: /runpod-volume/runpod-slim/ComfyUI/\n    checkpoints: models/checkpoints/\n    diffusion_models: models/diffusion_models/\n    vae: models/vae/\n    text_encoders: models/text_encoders/\n    audio_encoders: models/audio_encoders/\n    clip: models/clip/\n    loras: models/loras/\n    upscale_models: models/upscale_models/\n    latent_upscale_models: models/latent_upscale_models/\n" > /comfyui/extra_model_paths.yaml

# ── FIX : désactiver le nouveau système Dynamic VRAM (comfy-aimdo), suspecté ─
# ── de casser l'exécution après une boucle forLoopStart/forLoopEnd ──────────
RUN sed -i 's/--disable-metadata/--disable-metadata --disable-dynamic-vram/g' /start.sh && \
    echo "=== VERIFICATION DU PATCH ===" && grep -n "disable-dynamic-vram" /start.sh

# ── Démarrage : ComfyUI + handler ────────────────────────────────────────────
COPY rp_handler.py /handler.py