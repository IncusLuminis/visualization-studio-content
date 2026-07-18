#!/usr/bin/env zsh
set -euo pipefail

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# media-math.pages.dev is a Cloudflare Pages project with no GitHub connection —
# it only ever receives files via this direct upload. media-site/ is gitignored
# (see .gitignore) since it's heavy, non-diffable binary media; this script is
# the only way new animations reach the CDN.
#
# `wrangler pages deploy` walks the whole media-site/ tree to build its manifest,
# but it content-hashes each file first and only transfers bytes for hashes not
# already stored on Cloudflare — so an unchanged file is skipped, and a single
# changed/new file results in a single real upload. Wrangler's own output lists
# exactly what got uploaded, not the whole tree.
wrangler pages deploy "$ROOT/media-site" \
  --project-name media-math \
  --commit-dirty=true
