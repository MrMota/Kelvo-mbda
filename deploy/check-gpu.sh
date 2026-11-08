#!/usr/bin/env bash
# Checks that Ollama in Docker is really using your NVIDIA GPU.
# Run from the repo folder:  bash deploy/check-gpu.sh [model]
# Each step prints OK or FAIL with what to do next. Nothing is changed on your system.
set -u
MODEL="${1:-qwen3:30b}"
pass() { printf '  OK    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n        → %s\n' "$1" "$2"; exit 1; }

echo "1. NVIDIA driver on this machine"
command -v nvidia-smi >/dev/null || fail "nvidia-smi not found" "install the NVIDIA driver for your GPU, then reboot"
GPU=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
[ -n "$GPU" ] || fail "the driver doesn't see a GPU" "check 'nvidia-smi' by hand; reboot after a driver install"
pass "$GPU"

echo "2. Docker can hand the GPU to containers"
command -v nvidia-ctk >/dev/null || fail "NVIDIA Container Toolkit not installed" "follow 'Install the NVIDIA Container Toolkit' in replica/deploy.md"
docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L >/dev/null 2>&1 \
  || fail "a test container can't see the GPU" "run: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
pass "test container sees the GPU"

echo "3. Compose is set up for the GPU"
docker compose config 2>/dev/null | grep -q "driver: nvidia" \
  || fail "the GPU file isn't active" "add COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml to .env, then: docker compose up -d"
pass "docker-compose.gpu.yml is active"

echo "4. Ollama runs a model on the GPU"
docker compose ps --status running --services 2>/dev/null | grep -qx ollama || fail "the ollama service isn't running" "docker compose up -d"
docker compose exec -T ollama ollama list | awk 'NR>1{print $1}' | grep -qx "$MODEL" \
  || fail "$MODEL isn't pulled" "docker compose exec ollama ollama pull $MODEL   (or pass another model: bash deploy/check-gpu.sh <model>)"
docker compose exec -T ollama ollama run "$MODEL" "Reply with the single word: ready" >/dev/null 2>&1 \
  || fail "the model didn't answer" "docker compose logs ollama | tail -50"
PROC=$(docker compose exec -T ollama ollama ps | awk -v m="$MODEL" '$1==m' )
echo "        $PROC"
case "$PROC" in
  *"100% GPU"*) pass "$MODEL runs fully on the GPU" ;;
  *GPU*)        printf '  WARN  %s is split between CPU and GPU: it does not fit in VRAM\n        → pick a smaller model or a lower context window (see the VRAM table in replica/deploy.md)\n' "$MODEL" ;;
  *)            fail "$MODEL is running on the CPU" "docker compose logs ollama | grep -i -E 'cuda|gpu' ; then re-run steps 2-3" ;;
esac
echo "All good. Open http://127.0.0.1:7860 and pick $MODEL as the default model in Settings → Models."
