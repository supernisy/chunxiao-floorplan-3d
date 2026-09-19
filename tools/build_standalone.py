"""build_standalone.py — 把 app/dist 的构建产物打成**单文件 HTML**。

用途：不必起服务器、不必联网，双击即可在浏览器里看 3D 毛坯房演示，
也方便直接发给别人。产物：demo/chunxiao-3d-standalone.html

原理：vite 产物只有一个 ES module bundle，把它内联进 <script type="module"> 即可。
内联的 module 脚本不受 file:// 的 CORS 限制（外部 .js 才会被拦）。
"""
import re, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "app" / "dist"
OUT = ROOT / "demo" / "chunxiao-3d-standalone.html"


def main() -> int:
    html = (DIST / "index.html").read_text(encoding="utf-8")

    # 找到唯一的 bundle（dist/assets/index-*.js）
    jars = list((DIST / "assets").glob("index-*.js"))
    if len(jars) != 1:
        print(f"✗ 期望 1 个 bundle，实际 {len(jars)} 个：{jars}", file=sys.stderr)
        return 1
    bundle = jars[0]
    js = bundle.read_text(encoding="utf-8")

    # 防呆：内联脚本里若含 </script> 会提前闭合标签
    if "</script>" in js:
        print("✗ bundle 含 </script> 字面量，需转义后再内联", file=sys.stderr)
        return 1

    # 把 <script type="module" ... src="..."></script> 换成内联
    # ⚠️ 替换串含大量反斜杠/\\u 序列，必须用函数式 repl，否则被当 re 模板解析而报 bad escape
    patched, n = re.subn(
        r'<script[^>]*type="module"[^>]*src="[^"]*"[^>]*>\s*</script>',
        lambda _m: '<script type="module">\n' + js + '\n</script>',
        html,
    )
    if n != 1:
        print(f"✗ 未匹配到 module script 标签（匹配数={n}）", file=sys.stderr)
        return 1

    # 加一条离线提示（仅当通过 file:// 打开时显示），无副作用
    banner = (
        '<div id="__offline_hint" style="position:fixed;left:12px;bottom:12px;z-index:99;'
        'font:12px/1.6 system-ui;color:#8b949e;background:rgba(0,0,0,.45);'
        'padding:6px 10px;border-radius:6px;pointer-events:none">'
        '单文件离线版 · 拖拽旋转 / 滚轮缩放 · 支持 ?zoom=&cx=&cy=&tilt=</div>'
    )
    patched = patched.replace("<div id=\"root\"></div>",
                              "<div id=\"root\"></div>\n" + banner, 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patched, encoding="utf-8")
    print(f"✓ {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1048576:.2f} MB，内联 {bundle.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
