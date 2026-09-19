# AGENTS.md — 春晓户型「矢量 PDF → 3D 毛坯房」

> 给在这个仓库里干活的 AI/人看的约定。改动前先读这一页。

## 1. 这个项目在做什么

把 CAD 导出的**矢量 PDF 户型图**（`assets/chunxiao.pdf`）重建为**严格正交**的
可交互 3D 毛坯房：分层解析 → 户型包络 → 墙/房间分割 → 门窗按图例判读 →
2D 正交化 → 3D 渲染（Vite + React + react-three-fiber）。

## 2. 目录

| 路径 | 作用 |
|------|------|
| `pipeline/geom_v6.py` | **主管线**：墙掩膜 → 包络 → 洞口 → 房间分割 → 矢量化 → 写盘 |
| `pipeline/geom_v5.py` | 被 v6 复用的底层工具（图层读入、栅格化、轮廓→多边形） |
| `pipeline/triangulate_walls.py` | 墙体 CDT 预三角化，产出 `walls_tri.json`（绕开 three.js earcut） |
| `pipeline/make_plan6.py` | 「我的理解平面图」——画的是**管线实际产出的数据**，用于人工核对 |
| `pipeline/probe_region2.py` | 查 ROI 内所有矢量图元（图层/颜色/几何），判读歧义处用 |
| `pipeline/roi_pdf.py` | 渲染 ROI 的 PDF 原图并按图层高亮（`PLAIN=1` 看原图） |
| `app/src/data/*.json` | **数据契约**：`room-graph.json` / `walls_poly.json` / `walls_tri.json` / `roof_poly.json` |
| `app/src/App.jsx` | 3D 渲染 |
| `tools/capture.sh` | 一条命令自管理生命周期截图（vite + headless Edge CDP） |
| `tools/build_standalone.py` | 把 `app/dist` 打成**单文件 HTML**（`demo/chunxiao-3d-standalone.html`） |
| `tools/verify_standalone.sh` | `file://` 下渲染自检（像素方差判定，非肉眼） |
| `tools/shots.sh` | **一次**启动 vite+headless Edge，连拍多个视角（调相机 / 出交付图用，比逐张 capture.sh 快得多） |
| `tools/push_via_api.py` | `github.com` 被封锁时经 `api.github.com` 用 Git Data API 推送 |

## 3. 一键跑通

```bash
PY="C:/Users/super/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
$PY pipeline/geom_v6.py            # 重建 4 个数据文件
$PY pipeline/triangulate_walls.py  # 墙体三角化
$PY pipeline/make_plan6.py full    # 出理解图（full|master|gw）
bash tools/capture.sh "/" out.png 1600 1150 9000   # 截图
```

交付/演示链（改完前端务必走一遍，别让 demo 落后于源码）：

```bash
cd app && npx vite build                 # 1. 重新构建
cd .. && $PY tools/build_standalone.py   # 2. 重打单文件离线版
bash tools/verify_standalone.sh          # 3. 断言真的渲染出来了（PASS/FAIL）
```

调相机 / 出多张交付图时用 `tools/shots.sh`（只启一次 vite 与 Edge）：

```bash
bash tools/shots.sh "orbit=/" "top=?mode=top" "gw=?mode=top&zoom=3.2&cx=11.05&cy=3.0"
# -> data/v6/shot_orbit.png, shot_top.png, shot_gw.png
```

截图用的相机参数（`TopView` 支持）：`?zoom=` / `?cx=&cy=` / `?tilt=`（0=正俯视，>0=轴测）。
另有 `?mode=walk`（第一人称）、`?debug=wall|door|floor`（诊断单层）。

## 4. 人工裁定表（图纸判读的真值，改前先读注释）

判读有歧义处**不靠调参碰运气**，统一写在 `geom_v6.py` 顶部的裁定表里，每条注明 PDF 依据：

| 常量 | 作用 |
|------|------|
| `SEAL_SUPPRESS_ROI` | 抑制「补窄缝」产生的假封堵（公卫被纵切 / 飘窗被切走） |
| `SEAL_SUPPRESS_DOP_ROI` | 抑制飘窗带上被误判为门实例的**栏杆** |
| `SHAFT_ROI` | 管井整块丢弃（非户内可用空间） |
| `BAY_MERGE` | 飘窗并入其所属房间 |
| `DOOR_SIDE_FIX` | 门开向兜底（一般不需要，门扇法已够准） |

判读**约定**（不是裁定、而是图上惯例，写在 `wall_gap_extent()` 里）：

| 约定 | 依据 | 后果（若不做） |
|------|------|----------------|
| **推拉门洞口 = 两侧墙端之间的距离**，不是「门扇并集的跨度」 | 本图 3 樘移门校准：客厅阳台 4.365m 洞 / 4 扇并集 4.36m；小孩房阳台 1.85m 洞 / 并集 1.847m —— 并集**应当**等于洞宽 | 厨房推拉门被画成半开（并集仅 0.995m，东扇平移 0.566m 正好顶到东墙端头），3D 里右侧漏出 **0.57m 豁口**，既没墙也没门 |

## 5. 约定（重要）

### 5.1 提问必须带「落点」
**任何需要用户裁决的问题，必须写明：① 基于哪张图（文件名 / 图种）② 图上哪个编号
（房间 id 或门窗 id）③ 该处坐标或位置描述。**
反面教材：问「R10 是飘窗还是衣帽间」——用户不知道 R10 是哪张图的哪个位置，沟通成本极高。

理解图 `plan_v6_*.png` 上**每个房间都标了数据 id**，提问时直接引用即可。

### 5.2 数据 id 会变，别跨版本引用
房间 id（R0/R1…）是按面积排序生成的**位置无关编号**，重跑管线就会变。
跨版本沟通必须同时给**坐标或图**。旧编号与新编号的对照见 `plan_v6_full.png` 上的红框。

### 5.3 用户裁定优先于算法
用户看图纸给出的裁定（如「飘窗属于房间」「X 门是内开」）写进裁定表，
**不要**让算法再"自动纠正"回去。

### 5.4 正交性是不可退让的底线
非轴向边必须为 **0**（不是"轴率 93%"）。任何形态学操作都要用 1D 核
（`_axis_close`），buffer 必须显式 `join_style=2`（mitre），轮廓用 `CHAIN_APPROX_NONE`。

### 5.5 交付即演示（别停在"源码推上去了"）
每轮交付必须给出**可点的演示**，二选一（推荐都做）：

- 单文件离线版 `demo/chunxiao-3d-standalone.html`（双击即开、可转发）；
- 本地静态服务 `python -m http.server 5180 --bind 127.0.0.1 -d app/dist`。

**改了 `app/` 下的任何东西，都要重跑 §3 的交付链**，否则 demo 会落后于源码。
演示做完要**过一遍 `verify_standalone.sh`**（像素方差 PASS 才算数，不许"我觉得能开"）。

### 5.6 推送网络：`github.com` 不通时走 Git Data API
本机网络按主机名放行，`github.com:443` 可能整站不通（`git push` 报 `SSL_ERROR_SYSCALL`），
而 `api.github.com` 正常。此时**不要**反复重配凭据/改 URL/固定 IP——那些是错的层。
直接用 `python tools/push_via_api.py <owner/repo> [branch]`。
排查顺序与四个坑见 `~/.workbuddy/skills/git-push-fix`（v1.3.0 第 6 步）。

### 5.7 "洞口/缺口"类问题先问三件事
用户肉眼看出"某处不该空"时，按这个顺序查，别急着下结论：

1. **原始 PDF 里那块到底画了什么**——用 `probe_region2.py X0 Y0 X1 Y1 --all`（默认每层只打 12 条，
   排查"有没有画墙"必须加 `--all`，否则关键图元会被截掉），必要时再用 `roi_pdf.py`
   以 `PLAIN=1` 看全图层叠加原图；
2. **是"图画得怪"还是"我们读得怪"**——查该图层的惯例（例：推拉门画半开、门扇画在开启位置）；
3. **拿同图其它同类构件校准**——本图 3 樘移门互相对照才定下"并集应等于洞宽"。

→ 结论写进 §4 的表，**不要**只改代码留个魔法判断。

### 5.8 改 3D 视角/环境的默认值前先连拍
`tools/shots.sh` 一次启 vite+Edge 连拍多组参数，比逐张 `capture.sh` 快一个数量级。
取景参数（`?az= ?el= ?dist=`）改动后至少拍「默认 / 偏高 / 偏低」三张再定稿——
只凭一张图很容易定出"看不到天空"或"屋子太小"的默认值（本轮已踩）。

## 6. 当前状态

- 10 房间 / 11 门（平开 8 + 玻璃移门 3）/ 6 窗 / 套内 **125.18 m²**
- 移门洞口已撑到墙端：厨房 1.59m、客厅阳台 4.43m、小孩房阳台 1.91m（原先厨房只有 1.0m，
  右侧漏 0.57m 豁口）
- 房间非轴向边 = 0；公卫为完整 L 形（东北角管井凹角）
- 飘窗已并入主卧套间 / 瑶瑶衣帽间，渲染成 0.5m 抬高台面
- 门开向由 `P-DOOR` **橙色门扇质心**判读（比开启弧法稳）
- 默认视角 = **第三人称环视**（透视轨道相机，可旋转/缩放/平移）；
  另有 `?mode=top` 正交图纸视角、`?mode=walk` 第一人称漫游
- 套型按 **17/26 层**渲染外部环境：天空穹顶 + 地坪街道网格 + 两圈城市剪影 +
  半透明楼身（地坪 −48m → 本层 → 塔顶），俯视模式下自动关闭

### 已知遗留
1. 公卫的淋浴玻璃隔断（`COMM-GLAZ-SECT` 剖线）尚未在 3D 里单独渲染。
2. 公卫「盥洗龛」（洗手台，x11.33-11.90 / y3.67-4.52）**向客厅开敞**无结构墙，
   故几何上归属 LDK；3D 里尚未摆洗手台实体。
3. 外部环境是**程序化示意**（非真实城市 GIS 数据）——只表达"在 17 楼"，不代表实际周边。
4. `pipeline/rooms_v4.py` 的历史分割 bug 未查（已被 v6 管线取代，可忽略）。
