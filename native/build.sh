#!/usr/bin/env bash
# Build the virtual-pointer helper. Needs gcc, wayland-scanner, libwayland-client.
set -euo pipefail
cd "$(dirname "$0")"
XML=protocols/wlr-virtual-pointer-unstable-v1.xml
wayland-scanner client-header "$XML" wlr-virtual-pointer-unstable-v1-client-protocol.h
wayland-scanner private-code  "$XML" wlr-virtual-pointer-unstable-v1-protocol.c
gcc -O2 -Wall -Wextra -o vpointer vpointer.c wlr-virtual-pointer-unstable-v1-protocol.c \
    $(pkg-config --cflags --libs wayland-client)
echo "built $(pwd)/vpointer"
