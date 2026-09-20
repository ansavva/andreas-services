# studio's Wan 2.2 I2V worker, baked: the stock worker-comfyui image plus the
# two files runpod-endpoint-up.sh otherwise copies off the network volume at
# start. Code and deps only — the weights stay on the volume (README.md).
#
#   docker buildx build --platform linux/amd64 -t <registry>/studio-wan22:<tag> --push .
#   ./studio/scripts/runpod-endpoint-up.sh --image <registry>/studio-wan22:<tag>
#
# The tag must match runpod-common.sh's WAN22_IMAGE base: the handler drives
# the ComfyUI version that image carries (0.34.0: SaveVideo, WanFirstLastFrameToVideo).
FROM runpod/worker-comfyui:5.10.0-base

COPY extra_model_paths.yaml /comfyui/extra_model_paths.yaml
COPY handler.py /handler.py
COPY start.sh /studio-start.sh

# Baked means baked: an empty STUDIO_DIR stops start.sh copying a newer
# handler off the volume over the one in this image.
ENV STUDIO_DIR=""

# ComfyUI on 127.0.0.1:8188 with our flags, then /handler.py.
CMD ["bash", "/studio-start.sh"]
