#!/usr/bin/env bash
# shots.sh — 一次启动 vite + headless Edge(CDP)，连拍多个视角，最后统一清理。
# 用途：调相机参数 / 出一组交付截图时，避免每张都重启一遍服务与浏览器。
#
# 用法:
#   bash tools/shots.sh "orbit=?el=22&dist=2.0" "top=?mode=top" ...
#   W=1920 H=1200 WAIT=12000 bash tools/shots.sh "a=/?tilt=50"
#
# 产物: data/v6/shot_<NAME>.png
set -u
export PATH="/usr/bin:/bin:/c/Windows/System32:/c/Users/super/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH"
export no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost

ROOT="C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
NODE="C:/Users/super/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
EDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
PORT=5199
CDP=9333
PROFILE="$ROOT/data/_edge_profile"
W="${W:-1600}"; H="${H:-1000}"; WAIT="${WAIT:-12000}"

cleanup() {
  [ -n "${VITE_PID:-}" ] && kill "$VITE_PID" 2>/dev/null
  powershell -NoProfile -Command \
    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { \$_.CommandLine -like '*remote-debugging-port=$CDP*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" \
    >/dev/null 2>&1
}
trap cleanup EXIT

cd "$ROOT/app"
"$NODE" node_modules/vite/bin/vite.js --port $PORT --strictPort > "$ROOT/data/_vite.log" 2>&1 &
VITE_PID=$!
for i in $(seq 1 80); do
  curl -s --noproxy '*' "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && break
  sleep 0.4
done
echo "[shots] vite up on $PORT"

"$EDGE" --headless=new --disable-gpu --remote-debugging-port=$CDP \
  --user-data-dir="$PROFILE" --window-size=$W,$H --no-first-run \
  about:blank > "$ROOT/data/_edge.log" 2>&1 &
for i in $(seq 1 80); do
  curl -s --noproxy '*' "http://127.0.0.1:$CDP/json/version" >/dev/null 2>&1 && break
  sleep 0.4
done
echo "[shots] edge CDP up on $CDP"

for spec in "$@"; do
  name="${spec%%=*}"
  path="${spec#*=}"
  CDP_PORT=$CDP "$NODE" "$ROOT/tools/shot.mjs" \
    "http://127.0.0.1:$PORT$path" "$ROOT/data/v6/shot_$name.png" "$W" "$H" "$WAIT" 2>&1 | grep -v "React DevTools"
done
echo "[shots] done -> $ROOT/data/v6/shot_*.png"
