#!/bin/sh
# Turn the recorded clips into README GIFs: 12 fps, 900 px wide, a palette per clip.
set -eu
cd "$(dirname "$0")"
mkdir -p ../../docs/media
for webm in out/*.webm; do
  name=$(basename "$webm" .webm)
  ffmpeg -loglevel error -y -i "$webm" \
    -vf "fps=12,scale=900:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
    "../../docs/media/$name.gif"
  echo "docs/media/$name.gif $(du -k "../../docs/media/$name.gif" | cut -f1) KB"
done
