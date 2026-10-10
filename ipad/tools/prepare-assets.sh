#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"
npm ci --prefix web --ignore-scripts
web_assets=ipad/App/Web
rm -rf "$web_assets/cesium"
cp -R web/node_modules/cesium/Build/Cesium "$web_assets/cesium"
cp web/node_modules/milsymbol/dist/milsymbol.js "$web_assets/milsymbol.js"
cp web/symbology.js "$web_assets/symbology.js"
mkdir -p "$web_assets/licenses"
cp web/node_modules/cesium/LICENSE.md "$web_assets/licenses/Cesium-LICENSE.md"
cp web/node_modules/milsymbol/LICENSE "$web_assets/licenses/milsymbol-LICENSE"
cp ipad/ThirdPartyNotices.md "$web_assets/licenses/ThirdPartyNotices.md"
echo "Offline Cesium + Natural Earth II assets prepared."
