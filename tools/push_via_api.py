"""push_via_api.py — 当 `git push` 走不通（github.com 不可达）时，用 GitHub
Git Data API（api.github.com）把当前 HEAD 的完整文件树推上去。

为什么需要它
────────────────────────────────────────────────────────────
本机网络策略**按主机名放行**：`api.github.com` 可达（gh 能用），但
`github.com:443` 连不上 → `git push` 必然失败（SSL_ERROR_SYSCALL / 超时）。
而 gh 的 API 通道是通的，于是改用 Git Data API 造 commit：

    blobs(并发上传) → trees(逐级) → commit → 更新 ref

用法:  python tools/push_via_api.py <owner/repo> [branch] [--message-file FILE]

⚠️ 行尾归一化（第 12 轮踩过的坑）
────────────────────────────────────────────────────────────
本机 `core.autocrlf=true`：git **仓库里存的是 LF**，而工作区可能是 CRLF。
如果直接上传工作区原文，每个 CRLF 文本文件在远端都会被判成"已修改" ——
一次推送就污染二三十个文件（`data/*.json`、`pipeline/*.py` 全部"被改"），
`git log` 也脏掉。所以文本类文件上传前必须做 `\r\n -> \n`。
"""
import os, sys, json, base64, subprocess, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

GH = r"C:\Users\super\AppData\Local\gh_install\bin\gh.exe"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEBANG_MODE = 0o100755

# 需要 LF 归一化的文本类型（二进制如 .png/.pdf/.dwg 不动）
TEXT_EXT = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".sh", ".json",
            ".md", ".txt", ".svg", ".html", ".css", ".yml", ".yaml", ".toml", ".csv"}
TEXT_NAME = {".gitignore", ".gitattributes", ".editorconfig"}

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 绕开不可用代理


def token():
    out = subprocess.run([GH, "auth", "token"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("拿不到 gh token: " + out.stderr.strip())
    return out.stdout.strip()


TOKEN = token()


def req(method, path, body=None, retries=3):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for _ in range(retries):
        r = urllib.request.Request(url, data=data, method=method)
        r.add_header("Authorization", f"Bearer {TOKEN}")
        r.add_header("Accept", "application/vnd.github+json")
        r.add_header("User-Agent", "chunxiao-push-via-api")
        if data:
            r.add_header("Content-Type", "application/json")
        try:
            with _opener.open(r, timeout=90) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            last = f"HTTP {e.code} {path}: {detail}"
            if e.code in (422, 404):
                break
        except Exception as e:                                    # 网络抖动 -> 重试
            last = f"{type(e).__name__} {path}: {e}"
    raise RuntimeError(last)


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def upload_blob(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        raw = f.read()
    if os.path.splitext(rel)[1].lower() in TEXT_EXT or os.path.basename(rel) in TEXT_NAME:
        raw = raw.replace(b"\r\n", b"\n")          # 对齐 git 仓库里的 LF 存储
    content = base64.b64encode(raw).decode()
    sha = req("POST", f"/repos/{OWNER}/{REPO}/git/blobs",
              {"content": content, "encoding": "base64"})["sha"]
    return rel, sha


def build_tree(files, prefix=""):
    """自底向上建 tree（GitHub 的 tree 条目 path 只允许单层，故逐级来）。"""
    entries, subdirs = [], set()
    for p, sha in files.items():
        if not p.startswith(prefix):
            continue
        rest = p[len(prefix):]
        if "/" in rest:
            subdirs.add(rest.split("/")[0])
        else:
            # ⚠️ mode 必须是**字符串**（GitHub API 不接受整数 0o100644）
            mode = "100755" if rest.endswith((".sh", ".mjs")) else "100644"
            entries.append({"path": rest, "mode": mode, "type": "blob", "sha": sha})
    for sd in sorted(subdirs):
        sub_entries, sub_sha = build_tree(files, prefix + sd + "/")
        entries.append({"path": sd, "mode": "040000", "type": "tree", "sha": sub_sha})
    sha = req("POST", f"/repos/{OWNER}/{REPO}/git/trees", {"tree": entries})["sha"]
    print(f"  tree {prefix or '<root>':24s} {len(entries):3d} 项")
    return entries, sha


def main():
    global OWNER, REPO
    if len(sys.argv) < 2 or "/" not in sys.argv[1]:
        raise SystemExit(__doc__)
    OWNER, REPO = sys.argv[1].split("/", 1)
    branch = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "main"

    msg_file = None
    if "--message-file" in sys.argv:
        msg_file = sys.argv[sys.argv.index("--message-file") + 1]
    message = (open(msg_file, encoding="utf-8").read() if msg_file
               else subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=ROOT,
                                   capture_output=True, text=True).stdout.strip())

    files = tracked_files()
    total = sum(os.path.getsize(os.path.join(ROOT, f)) for f in files
                if os.path.isfile(os.path.join(ROOT, f)))
    print(f"[1/4] 上传 blobs：{len(files)} 个文件 / {total/1048576:.2f} MB")
    shas = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (rel, sha) in enumerate(ex.map(upload_blob, files), 1):
            shas[rel] = sha
            if i % 25 == 0 or i == len(files):
                print(f"      {i}/{len(files)}")

    print("[2/4] 建 tree")
    _, root_sha = build_tree(shas)

    print("[3/4] 建 commit")
    who = {"name": "supernisy", "email": "supernisy@users.noreply.github.com"}
    # --orphan：不带 parent，直接以本次内容作为该分支的唯一根提交
    # （GitHub 对「空仓库」不允许建 blob，所以必须先有一个占位 commit 才能开工；
    #   占位 commit 不进历史，用 force 更新 ref 把它顶掉）
    parents = []
    if "--orphan" not in sys.argv:
        try:
            parents = [req("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{branch}")["object"]["sha"]]
        except Exception:
            print("      （远端尚无该分支，作为首个 commit）")
    commit = req("POST", f"/repos/{OWNER}/{REPO}/git/commits",
                 {"message": message, "tree": root_sha, "parents": parents,
                  "author": who, "committer": who})

    print("[4/4] 更新 ref")
    if parents:
        req("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{branch}",
            {"sha": commit["sha"], "force": True})
    elif "--orphan" in sys.argv:
        req("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{branch}",
            {"sha": commit["sha"], "force": True})       # 顶掉占位 commit
    else:
        req("POST", f"/repos/{OWNER}/{REPO}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    print(f"DONE  https://github.com/{OWNER}/{REPO}  {commit['sha'][:8]}")


if __name__ == "__main__":
    main()
