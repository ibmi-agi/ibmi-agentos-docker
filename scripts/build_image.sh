#!/bin/bash

############################################################################
#
#    Agno Docker Image Builder
#
#    Usage: ./scripts/build_image.sh [--push]
#
#    Options:
#      --push    Build for linux/amd64,linux/arm64 and push to registry
#
#    Without --push, builds for the native platform only (no QEMU needed).
#
#    Prerequisites:
#      - Docker Buildx installed
#      - Run 'docker buildx create --use' first (for --push)
#
############################################################################

set -e

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_ROOT="$(dirname "${CURR_DIR}")"
DOCKER_FILE="Dockerfile"
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
echo -e "    ${ORANGE}▸${NC} ${BOLD}Building Docker image${NC}"
echo -e "    ${DIM}Image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"

if [ "$PUSH" = true ]; then
    PLATFORMS="linux/amd64,linux/arm64"
    echo -e "    ${DIM}Platforms: ${PLATFORMS}${NC}"
    echo ""
    echo -e "    ${DIM}> docker buildx build --platform=${PLATFORMS} -t ${IMAGE_NAME}:${IMAGE_TAG} -f ${DOCKER_FILE} ${OS_ROOT} --push${NC}"
    docker buildx build --platform=${PLATFORMS} -t ${IMAGE_NAME}:${IMAGE_TAG} -f ${DOCKER_FILE} ${OS_ROOT} --push
else
    echo -e "    ${DIM}Platform: native (use --push for multi-platform)${NC}"
    echo ""
    echo -e "    ${DIM}> docker buildx build -t ${IMAGE_NAME}:${IMAGE_TAG} -f ${DOCKER_FILE} ${OS_ROOT} --load${NC}"
    docker buildx build -t ${IMAGE_NAME}:${IMAGE_TAG} -f ${DOCKER_FILE} ${OS_ROOT} --load
fi

echo ""
echo -e "    ${BOLD}Done.${NC}"
echo ""