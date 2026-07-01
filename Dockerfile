FROM runpod/worker-comfyui:5.8.5-base

# ── Custom nodes via comfy-cli (registry officiel) ──────────────────────────
RUN comfy node install \
    comfyui-kjnodes \
    comfyui-videohelpersuite \
    comfyui-easy-use \
    comfyui-impact-pack \
    comfyui-frame-interpolation \
    rgthree-comfy \
    comfyui_essentials \
    comfy-mtb \
    comfyui-gguf

# ── Custom nodes via git clone (hors registry ou version spécifique) ─────────

# RES4LYF — samplers avancés LTX
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/ClownsharkBatwing/RES4LYF.git && \
    cd RES4LYF && pip install -r requirements.txt || true

# ComfyUI-MelBandRoFormer — séparation voix/musique
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-MelBandRoformer.git && \
    cd ComfyUI-MelBandRoformer && pip install -r requirements.txt || true

# ComfyUI_StarNodes — nodes utilitaires
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/Starnodes2024/ComfyUI_StarNodes.git && \
    cd ComfyUI_StarNodes && pip install -r requirements.txt || true

# ComfyUI_Swwan — resize et crop nodes
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/aining2022/ComfyUI_Swwan.git && \
    cd ComfyUI_Swwan && pip install -r requirements.txt || true

# ComfyUI_JomaNodes — math et switch nodes
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/jomakaze/ComfyUI_JomaNodes.git && \
    cd ComfyUI_JomaNodes && pip install -r requirements.txt || true

# CRT-Nodes
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/crt-nodes/crt-nodes.git && \
    cd crt-nodes && pip install -r requirements.txt || true

# ComfyUI vsLinx Nodes
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/vslinx/comfyui-vslinx-nodes.git && \
    cd comfyui-vslinx-nodes && pip install -r requirements.txt || true

# ComfyUI_Ib_CustomNodes
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/Chaoses-Ib/ComfyUI_Ib_CustomNodes.git && \
    cd ComfyUI_Ib_CustomNodes && pip install -r requirements.txt || true

RUN printf "comfyui:\n    base_path: /runpod-volume/runpod-slim/ComfyUI/\n    checkpoints: models/checkpoints/\n    diffusion_models: models/diffusion_models/\n    vae: models/vae/\n    text_encoders: models/text_encoders/\n    audio_encoders: models/audio_encoders/\n    clip: models/clip/\n    loras: models/loras/\n    upscale_models: models/upscale_models/\n" > /comfyui/extra_model_paths.yaml
