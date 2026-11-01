#!/bin/sh
# Turn the recorded clips into README GIFs: 8 fps, 720 px wide, 48 colours per clip (about 2 MB each).
set -eu
cd "$(dirname "$0")"
mkdir -p ../../docs/media
for webm in out/*.webm; do
  name=$(basename "$webm" .webm)
  ffmpeg -loglevel error -y -i "$webm" \
    -vf "fps=8,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
    "../../docs/media/$name.gif"
  echo "docs/media/$name.gif $(du -k "../../docs/media/$name.gif" | cut -f1) KB"
done
