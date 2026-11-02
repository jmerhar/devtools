#!/usr/bin/env bash
# Render the home-screen icons from an SVG.
#
# The PNGs are committed, so building needs no SVG renderer; run this after changing the drawing.
# 192 and 512 are the sizes a web manifest names; 180 is the size iOS asks of apple-touch-icon.
#
#   [icons]
#   svg = "frontend/icons/app-icon.svg"
#   out = "frontend/public/icons"
#   background = "#2f6f5e"                  # optional; transparent without it
#
# Usage: .devtools/bin/app-icons.sh    (from the repository root; needs rsvg-convert, from librsvg)
#   RSVG_CONVERT   the rsvg-convert command (default: rsvg-convert)
set -euo pipefail

here="$(dirname "$0")"
rsvg="${RSVG_CONVERT:-rsvg-convert}"

svg=$(python3 "$here/devtools-config.py" icons.svg)
out=$(python3 "$here/devtools-config.py" icons.out)
background=$(python3 "$here/devtools-config.py" --default "" icons.background)
colour=()
[ -n "$background" ] && colour=(--background-color "$background")
[ -f "$svg" ] || { echo "app-icons: $svg is missing" >&2; exit 1; }

mkdir -p "$out"
for size in 192 512; do
  "$rsvg" "${colour[@]}" --width "$size" --height "$size" "$svg" --output "$out/icon-$size.png"
done
"$rsvg" "${colour[@]}" --width 180 --height 180 "$svg" --output "$out/apple-touch-icon.png"
echo "app-icons: wrote icon-192.png, icon-512.png and apple-touch-icon.png in $out"
