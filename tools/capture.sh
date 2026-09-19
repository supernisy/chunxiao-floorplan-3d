#!/usr/bin/env bash
# capture.sh — 一条命令内自管理生命周期：起 vite dev -> 起 headless Edge(CDP) -> 截图 -> 清理
# 用法: bash tools/capture.sh [urlPath] [outPng] [W] [H] [waitMs]
#   urlPath 例: "/" 或 "/?debug=wall"
set -u
export PATH="/c/Users/super/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH"
export no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost

ROOT="C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
NODE="C:/Users/super/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
EDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
PORT=5199
CDP=9333
PROFILE="$ROOT/data/_edge_profile"

URLPATH="${1:-/}"
OUT="${2:-$ROOT/data/shot.png}"
W="${3:-1600}"; H="${4:-1000}"; WAIT="${5:-8000}"

cleanup() {
  kill "$VITE_PID" 2>/dev/null
  # 只杀带我们调试端口的 Edge，避免误伤用户正在用的 Edge
  powershell -NoProfile -Command \
    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { \$_.CommandLine -like '*remote-debugging-port=$CDP*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" \
    >/dev/null 2>&1
}
trap cleanup EXIT

# 1) vite
cd "$ROOT/app"
"$NODE" node_modules/vite/bin/vite.js --port $PORT --strictPort > "$ROOT/data/_vite.log" 2>&1 &
VITE_PID=$!
for i in $(seq 1 80); do
  curl -s --noproxy '*' "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && break
  sleep 0.4
done
echo "[capture] vite up on $PORT (pid $VITE_PID)"

# 2) headless edge + CDP
"$EDGE" --headless=new --disable-gpu --remote-debugging-port=$CDP \
  --user-data-dir="$PROFILE" --window-size=$W,$H --no-first-run \
  about:blank > "$ROOT/data/_edge.log" 2>&1 &
for i in $(seq 1 80); do
  curl -s --noproxy '*' "http://127.0.0.1:$CDP/json/version" >/dev/null 2>&1 && break
  sleep 0.4
done
echo "[capture] edge CDP up on $CDP"

# 3) shot
CDP_PORT=$CDP "$NODE" "$ROOT/tools/shot.mjs" \
  "http://127.0.0.1:$PORT$URLPATH" "$OUT" "$W" "$H" "$WAIT"
echo "[capture] -> $OUT"
