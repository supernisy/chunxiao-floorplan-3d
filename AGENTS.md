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

## 3. 一键跑通

```bash
PY="C:/Users/super/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
$PY pipeline/geom_v6.py            # 重建 4 个数据文件
$PY pipeline/triangulate_walls.py  # 墙体三角化
$PY pipeline/make_plan6.py full    # 出理解图（full|master|gw）
bash tools/capture.sh "/" out.png 1600 1150 9000   # 截图
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

## 6. 当前状态

- 10 房间 / 11 门（平开 8 + 玻璃移门 3）/ 6 窗 / 套内 **125.18 m²**
- 房间非轴向边 = 0；公卫为完整 L 形（东北角管井凹角）
- 飘窗已并入主卧套间 / 瑶瑶衣帽间，渲染成 0.5m 抬高台面
- 门开向由 `P-DOOR` **橙色门扇质心**判读（比开启弧法稳）

### 已知遗留
1. 公卫的淋浴玻璃隔断（`COMM-GLAZ-SECT` 剖线）尚未在 3D 里单独渲染。
2. 公卫「盥洗龛」（洗手台，x11.33-11.90 / y3.67-4.52）**向客厅开敞**无结构墙，
   故几何上归属 LDK；3D 里尚未摆洗手台实体。
3. `pipeline/rooms_v4.py` 的历史分割 bug 未查（已被 v6 管线取代，可忽略）。
