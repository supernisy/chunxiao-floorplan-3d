#!/usr/bin/env bash
# verify_standalone.sh — 校验「单文件离线演示页」在 file:// 下能否真实渲染。
# 一条命令内自管理生命周期：起 headless Edge(CDP) -> 打开 file:// 单文件 -> 截图 -> 清理。
# 用法: bash tools/verify_standalone.sh [outPng] [query]
set -u
export PATH="/usr/bin:/bin:/c/Windows/System32:/c/Users/super/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH"
export no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost

ROOT="C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
NODE="C:/Users/super/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
PY="C:/Users/super/.workbuddy/binaries/python/envs/default/Scripts/python.exe"  # 含 PIL/cv2/pymupdf 的管线 venv
EDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
CDP=9334
PROFILE="$ROOT/data/_edge_profile_verify"
FILE="$ROOT/demo/chunxiao-3d-standalone.html"
OUT="${1:-$ROOT/data/standalone_check.png}"
Q="${2:-}"
W=1600; H=1000

cleanup() {
  powershell -NoProfile -Command \
    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { \$_.CommandLine -like '*remote-debugging-port=$CDP*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" \
    >/dev/null 2>&1
}
trap cleanup EXIT

# file:// URL（Git Bash 的 /c/... 要转成 file:///C:/...）
WIN="$FILE"
URL="file:///$WIN$Q"
echo "[verify] open $URL"

"$EDGE" --headless=new --disable-gpu --remote-debugging-port=$CDP \
  --user-data-dir="$PROFILE" --window-size=$W,$H --no-first-run \
  --allow-file-access-from-files about:blank > "$ROOT/data/_edge_verify.log" 2>&1 &
for i in $(seq 1 80); do
  curl -s --noproxy '*' "http://127.0.0.1:$CDP/json/version" >/dev/null 2>&1 && break
  sleep 0.4
done

CDP_PORT=$CDP "$NODE" "$ROOT/tools/shot.mjs" "$URL" "$OUT" "$W" "$H" 9000
echo "[verify] shot -> $OUT"

# 像素方差判定：真有 3D 渲染 => 大量渐变/多色；白屏/黑屏 => 方差≈0
"$PY" - "$OUT" <<'PYEOF'
import sys, warnings
warnings.filterwarnings("ignore")
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
w, h = im.size
px = im.resize((w//4, h//4)).getdata()          # 降采样加速
n = len(px)
avg = [sum(c[i] for c in px)/n for i in range(3)]
var = sum((c[i]-avg[i])**2 for c in px for i in range(3))/n
ok = var > 500                                   # 白屏/黑屏方差≈0；实测渲染场景 ≈2000
print(f"[verify] 均值RGB=({avg[0]:.0f},{avg[1]:.0f},{avg[2]:.0f})  方差={var:.0f}")
print("[verify] " + ("PASS 已渲染" if ok else "FAIL 疑似白屏/黑屏未渲染"))
sys.exit(0 if ok else 2)
PYEOF
