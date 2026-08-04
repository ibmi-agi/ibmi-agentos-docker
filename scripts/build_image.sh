#!/bin/bash

############################################################################
#
#    Agno Image Builder (Podman)
#
#    Usage: ./scripts/build_image.sh [--push]
#
#    Options:
#      --push    Build linux/amd64 + linux/arm64 into a manifest and push it
#
#    Without --push, builds for the native platform only (no QEMU needed).
#
#    Prerequisites:
#      - Podman installed (the podman machine ships QEMU for cross-arch)
#      - For --push: a registry-qualified IMAGE_NAME and `podman login`
#
############################################################################

set -e

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_ROOT="$(dirname "${CURR_DIR}")"
CONTAINER_FILE="Dockerfile"
IMAGE_NAME="ibmi-agentos-platform"
IMAGE_TAG="latest"

# Colors
ORANGE='\033[38;5;208m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

PUSH=false
for arg in "$@"; do
    case "$arg" in
        --push) PUSH=true ;;
    esac
done

echo ""
echo -e "    ${ORANGE}▸${NC} ${BOLD}Building image with Podman${NC}"
echo -e "    ${DIM}Image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"

if [ "$PUSH" = true ]; then
    PLATFORMS="linux/amd64,linux/arm64"
    echo -e "    ${DIM}Platforms: ${PLATFORMS}${NC}"
    echo ""
    echo -e "    ${DIM}> podman build --platform=${PLATFORMS} --manifest ${IMAGE_NAME}:${IMAGE_TAG} -f ${CONTAINER_FILE} ${OS_ROOT}${NC}"
    podman build --platform=${PLATFORMS} --manifest ${IMAGE_NAME}:${IMAGE_TAG} -f ${CONTAINER_FILE} ${OS_ROOT}
    echo -e "    ${DIM}> podman manifest push --all ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    podman manifest push --all ${IMAGE_NAME}:${IMAGE_TAG}
else
    echo -e "    ${DIM}Platform: native (use --push for multi-platform)${NC}"
    echo ""
    echo -e "    ${DIM}> podman build -t ${IMAGE_NAME}:${IMAGE_TAG} -f ${CONTAINER_FILE} ${OS_ROOT}${NC}"
    podman build -t ${IMAGE_NAME}:${IMAGE_TAG} -f ${CONTAINER_FILE} ${OS_ROOT}
fi

echo ""
echo -e "    ${BOLD}Done.${NC}"
echo ""
