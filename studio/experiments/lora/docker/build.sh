#!/usr/bin/env bash
# Build and push the lora-lab pod image to ECR, creating the repository and
# its RunPod pull policy on first run.
#
# One-time manual step this script cannot do: register the ECR registry in
# the RunPod console (Settings -> Container Registry Authentication). RunPod
# validates the cross-account delegation at registration, so do it AFTER the
# first successful run of this script — the policy has to exist first.
#
# The image is rebuilt rarely (a ComfyUI bump, a new custom node); weights
# never pass through here. On an Apple Silicon Mac the linux/amd64 build runs
# under QEMU emulation — insightface compiles a cython extension, so expect
# the first build to take a while. Layers cache; later builds are quick.
set -euo pipefail

cd "$(dirname "$0")"
LAB_ROOT=$(cd .. && pwd)

REGION=us-east-1
ACCOUNT=704202188703
REPO=lora-lab-pod
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
RUNPOD_ACCOUNT=550005742258   # RunPod's AWS account; its roles pull the image

log() { printf '\n=== %s ===\n' "$*"; }

# ---------------------------------------------------------------- ECR repo
log "ECR repository $REPO"
if ! aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" \
     > /dev/null 2>&1; then
  aws ecr create-repository --repository-name "$REPO" --region "$REGION" \
    --tags Key=Project,Value=studio Key=Environment,Value=dev \
           Key=Owner,Value=ansavva Key=ManagedBy,Value=lora-lab > /dev/null
  echo "  created"
else
  echo "  exists"
fi

# The RunPod pull delegation, VERBATIM from
# docs.runpod.io/tutorials/pods/use-private-ecr-images — RunPod validates this
# exact delegation shape when the credential is registered in its console, so
# the two deployment-role ARNs are theirs to name, not ours to widen. No token
# expiry to manage: RunPod's roles authenticate themselves per pull.
log "repository policy (RunPod pull delegation)"
aws ecr set-repository-policy --repository-name "$REPO" --region "$REGION" \
  --policy-text "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Sid\": \"AllowRunpodPull\",
      \"Effect\": \"Allow\",
      \"Principal\": \"*\",
      \"Action\": [
        \"ecr:GetAuthorizationToken\",
        \"ecr:BatchCheckLayerAvailability\",
        \"ecr:GetDownloadUrlForLayer\",
        \"ecr:BatchGetImage\"
      ],
      \"Condition\": {
        \"StringEquals\": {
          \"aws:PrincipalArn\": [
            \"arn:aws:iam::$RUNPOD_ACCOUNT:role/prod-us-east-1-deployment-role\",
            \"arn:aws:iam::$RUNPOD_ACCOUNT:role/prod-us-west-2-deployment-role\"
          ]
        }
      }
    }]
  }" > /dev/null
echo "  set"

# ---------------------------------------------------------------- pin ComfyUI
# A concrete commit, recorded in docker/COMFY_REF so a rebuild is
# deterministic — resolving HEAD per run moved the pin mid-night on
# 2026-08-25 and invalidated every cached layer. Bump by editing that file
# (or COMFY_REF=<sha> for a one-off).
if [ -z "${COMFY_REF:-}" ]; then
  if [ -f COMFY_REF ]; then
    COMFY_REF=$(cat COMFY_REF)
  else
    COMFY_REF=$(git ls-remote https://github.com/comfyanonymous/ComfyUI HEAD | cut -f1)
  fi
fi
echo "$COMFY_REF" > COMFY_REF
log "ComfyUI pinned at $COMFY_REF"

TAG="$(date +%Y%m%d)-${COMFY_REF:0:7}"
IMAGE="$REGISTRY/$REPO:$TAG"

# ---------------------------------------------------------------- context
# Staged, never the lab root: a build context that included local/ would ship
# subject data to the docker daemon. Only generic pod-side material enters.
log "staging build context"
rm -rf .context
mkdir -p .context/lab
cp entrypoint.sh .context/lab/
cp "$LAB_ROOT/assets/pod-assets.sh" .context/lab/
cp -R "$LAB_ROOT/assets/pod-scripts" .context/lab/pod-scripts

# ---------------------------------------------------------------- build+push
# An isolated DOCKER_CONFIG keeps the login out of Docker Desktop's keychain
# helper (docker-credential-desktop), which hung indefinitely on the first run
# of this script (2026-08-24). The ECR token is 12h-lived and the dir is
# removed below, so plain-text storage here is fine.
export DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf "$DOCKER_CONFIG" .context' EXIT
# The fresh config also loses Docker Desktop's CLI plugin path, taking
# `docker buildx` with it — point back at Desktop's plugins explicitly.
cat > "$DOCKER_CONFIG/config.json" <<'JSON'
{"cliPluginsExtraDirs": ["/Applications/Docker.app/Contents/Resources/cli-plugins"]}
JSON
# ...and the Desktop context selection, so name the daemon socket directly.
export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"
log "docker login $REGISTRY"
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$REGISTRY"

log "buildx $IMAGE (linux/amd64)"
# --provenance/--sbom off: buildx otherwise wraps the image in an OCI index
# with an extra attestation manifest. RunPod pulled that index fine on
# 2026-08-25 (the first boot failed on CUDA, not the manifest), so this is
# hygiene rather than a fix: a plain single manifest, nothing for any
# runtime to trip on.
docker buildx build \
  --provenance=false --sbom=false \
  --platform linux/amd64 \
  --build-arg COMFY_REF="$COMFY_REF" \
  -f Dockerfile \
  -t "$IMAGE" \
  --push \
  .context

rm -rf .context

# The CLI reads this file for the image to rent — adapters/runpod.py.
echo "$IMAGE" > IMAGE
log "pushed $IMAGE (recorded in docker/IMAGE)"
echo "If this was the first push: register the registry in the RunPod console"
echo "(Settings -> Container Registry Authentication) before 'lora-lab pod up'."
