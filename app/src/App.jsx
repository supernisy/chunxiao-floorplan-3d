import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrthographicCamera, OrbitControls, PointerLockControls, PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'
import graph from './data/room-graph.json'
import wallsPoly from './data/walls_poly.json'
import wallsTri from './data/walls_tri.json'
import roofData from './data/roof_poly.json'

const H_WALL = 2.9          // 层高
const H_DOOR = 2.12         // 门高
const WALL_T = 0.13         // 门楣厚度
const EYE = 1.62            // 视高
const SPEED = 3.6           // m/s

/* ---------- 楼层语境 ----------
   套型位于 17/26 层：地面在脚下 (17-1) 层处，头顶还有 (26-17) 层。
   渲染外部环境时以这两个常量定位地面与塔楼顶，让"在 17 楼"一眼可读。 */
const H_FLOOR = 3.0                          // 标准层层高（结构层高，比净高 2.9 略大）
const FLOOR_NO = 17                          // 本套所在层
const FLOOR_TOTAL = 26                       // 总层数
const GROUND_Y = -(FLOOR_NO - 1) * H_FLOOR   // 室外地坪 = -48 m
const TOWER_TOP_Y = (FLOOR_TOTAL - FLOOR_NO) * H_FLOOR + H_WALL  // 塔楼顶 ≈ +29.9 m

/* ---------- 工具 ---------- */
// 平面图 (x,y) -> three xz 平面：shape 用 (x, -y)，再 rotation.x = -90°
function shapeFrom(poly) {
  const s = new THREE.Shape()
  if (!poly || !poly.length) return s
  s.moveTo(poly[0][0], -poly[0][1])
  for (let i = 1; i < poly.length; i++) s.lineTo(poly[i][0], -poly[i][1])
  s.closePath()
  return s
}

/* ---------- 地面 ---------- */
const TINT = {
  LDK客餐厅厨房: '#e3e6ee', 主卧套间: '#e0ead9', 小孩房: '#efe0e8', 书房: '#dde6f2',
  公卫: '#dfeef2', 主卫: '#dfeef2', 次卫: '#dfeef2',
  客厅阳台: '#efe9d5', 小孩房阳台: '#efe9d5', 瑶瑶衣帽间: '#e9e3ef',
  电梯厅: '#e6e2dc', 楼梯间: '#e6e2dc', 消防电梯: '#dcd8d2', 普通电梯: '#dcd8d2',
  主卧飘窗: '#ece5f2', 小孩房飘窗: '#ece5f2',
}
const tint = (n) => TINT[n] || '#e8e8e8'

function RoomFloor({ poly, name }) {
  const shape = useMemo(() => shapeFrom(poly), [poly])
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]} receiveShadow>
      <shapeGeometry args={[shape]} />
      <meshStandardMaterial color={tint(name)} roughness={0.96} metalness={0} />
    </mesh>
  )
}

/* ---------- 墙体：CDT 预三角化顶面 + 轮廓侧壁（绕开 earcut） ----------
   ⚠️ 不用 ExtrudeGeometry：它内部走 earcut，在极瘦凹多边形+洞上会产出
   穿透墙体的退化三角形（俯视图里的黑三角尖刺）。
   这里顶面直接用 Python 侧 Shewchuk CDT 预三角化的结果，侧壁用轮廓边拉伸。
   坐标：平面 (x,y) -> three (x, height, y)。 */
function WallBand({ poly, tri }) {
  const geo = useMemo(() => {
    const H = tri?.height_m || H_WALL
    const pos = []
    // 顶面：CDT 三角形
    if (tri && tri.triangles) {
      const v = tri.vertices
      for (const [i, j, k] of tri.triangles) {
        for (const idx of [i, j, k]) pos.push(v[idx][0], H, v[idx][1])
      }
    }
    // 侧壁：轮廓环每条边拉成竖直四边形
    const rings = [poly.shell, ...(poly.holes || [])]
    for (const ring of rings) {
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i], b = ring[(i + 1) % ring.length]
        pos.push(a[0], 0, a[1], b[0], 0, b[1], b[0], H, b[1])
        pos.push(a[0], 0, a[1], b[0], H, b[1], a[0], H, a[1])
      }
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    g.computeVertexNormals()
    return g
  }, [poly, tri])
  return (
    <mesh geometry={geo} castShadow receiveShadow>
      <meshStandardMaterial color="#b3afa9" roughness={0.92} metalness={0} side={THREE.DoubleSide} />
    </mesh>
  )
}

/* ---------- 门：按类型参数化 ----------
   类型来自 PDF 图例的矢量判读（见 pipeline/geom_v6.py 顶部说明）：
     swing   平开门  —— P-DOOR 橙 + 开启弧 + 近正方形 bbox
     sliding 玻璃移门 —— P-DOOR 2~4 个平行错开细长矩形、无弧（厨房阳台 / 客厅阳台 / 小孩房阳台）
     window  窗      —— COMM-GLAZ-SECT 棕色玻璃剖线（在 windows 数组，不走这里）
   注意：sliding 必须单独渲染成**多扇错开的玻璃推拉门**，不能退化成"洞口"——
        否则厨房阳台会看起来是个 1m 宽的空洞，与图纸完全不符。 */
function doorKind(door, roomNameOf) {
  if (door.type === 'swing') return 'swing'
  if (door.type === 'sliding') return 'glazing'
  const names = (door.rooms || []).map(roomNameOf)
  if (names.some((n) => n && n.includes('阳台'))) return 'glazing'
  if (names.some((n) => n && n.includes('电梯'))) return 'lift'
  return 'opening'
}

/* 玻璃移门：按宽度切成 n 扇（每扇 ~1.1m），相邻扇沿门洞法线**错开**，
   模拟推拉门的轨道错位。 */
function GlazingUnit({ mid, ux, uy, rotY, L }) {
  const n = Math.max(2, Math.min(5, Math.round(L / 1.1)))
  const pane = L / n
  const nx = -uy      // 门洞法线
  const ny = ux
  return (
    <>
      {Array.from({ length: n }).map((_, i) => {
        const t = -L / 2 + pane * (i + 0.5)
        const off = (i % 2 === 0 ? -1 : 1) * 0.035
        return (
          <mesh key={i}
            position={[mid[0] + ux * t + nx * off, H_DOOR / 2, mid[1] + uy * t + ny * off]}
            rotation={[0, rotY, 0]}>
            <boxGeometry args={[pane - 0.03, H_DOOR - 0.10, 0.026]} />
            <meshPhysicalMaterial color="#bfe3ef" transparent opacity={0.30} roughness={0.08}
              metalness={0} transmission={0.65} side={THREE.DoubleSide} />
          </mesh>
        )
      })}
      {/* 轨道/下槛 */}
      <mesh position={[mid[0], 0.02, mid[1]]} rotation={[0, rotY, 0]}>
        <boxGeometry args={[L, 0.04, 0.10]} />
        <meshStandardMaterial color="#9a948e" roughness={0.7} />
      </mesh>
    </>
  )
}

function DoorUnit({ door, roomNameOf }) {
  const h = door.hinge_m
  const e = door.opening_m[1]
  const dx = e[0] - h[0]
  const dy = e[1] - h[1]
  const L = Math.hypot(dx, dy) || door.width_m
  const ux = dx / L
  const uy = dy / L
  const rotY = Math.atan2(-uy, ux)          // 局部 x 轴对齐门洞方向
  const mid = [(h[0] + e[0]) / 2, (h[1] + e[1]) / 2]
  const kind = doorKind(door, roomNameOf)
  const lintelH = H_WALL - H_DOOR

  return (
    <group>
      {/* 门楣 */}
      <mesh position={[mid[0], H_DOOR + lintelH / 2, mid[1]]} rotation={[0, rotY, 0]} castShadow>
        <boxGeometry args={[L, lintelH, WALL_T]} />
        <meshStandardMaterial color="#b3afa9" roughness={0.92} />
      </mesh>

      {/* 门套/框 */}
      {[-1, 1].map((s) => (
        <mesh key={s} position={[mid[0] + ux * (L / 2) * s, H_DOOR / 2, mid[1] + uy * (L / 2) * s]}
          rotation={[0, rotY, 0]}>
          <boxGeometry args={[0.05, H_DOOR, WALL_T + 0.02]} />
          <meshStandardMaterial color="#8f6f4e" roughness={0.7} />
        </mesh>
      ))}

      {/* 平开门：开向由数据里的 door.side 决定（+1 / -1），
          来自 geom_v6 对 P-DOOR 橙色门扇**质心**的判读 —— 门扇画在实际
          开启位置，质心必落在开门那一侧。此前这里写死 -π/3，导致
          衣帽间 / 主卫的门开向与图纸相反。 */}
      {kind === 'swing' && (
        <group position={[h[0], 0, h[1]]}
          rotation={[0, rotY - (door.side ?? 1) * Math.PI / 3, 0]}>
          <mesh position={[door.width_m / 2, H_DOOR / 2, 0]} castShadow>
            <boxGeometry args={[door.width_m, H_DOOR - 0.04, 0.045]} />
            <meshStandardMaterial color="#b98a5e" roughness={0.6} />
          </mesh>
          {/* 门把手 */}
          <mesh position={[door.width_m - 0.12, 1.05, 0.05]}>
            <sphereGeometry args={[0.035, 12, 12]} />
            <meshStandardMaterial color="#c9a227" metalness={0.8} roughness={0.3} />
          </mesh>
        </group>
      )}

      {kind === 'glazing' && (
        <GlazingUnit mid={mid} ux={ux} uy={uy} rotY={rotY} L={L} />
      )}

      {kind === 'lift' && (
        <mesh position={[mid[0], H_DOOR / 2, mid[1]]} rotation={[0, rotY, 0]}>
          <boxGeometry args={[L - 0.06, H_DOOR - 0.06, 0.06]} />
          <meshStandardMaterial color="#9aa3aa" metalness={0.85} roughness={0.35} />
        </mesh>
      )}
    </group>
  )
}

/* ---------- 窗：玻璃剖线（COMM-GLAZ-SECT）判读出的窗洞 ----------
   原先 graph.windows 根本没被消费（窗在 3D 里完全缺失）。
   毛坯房按「窗台墙 + 玻璃 + 窗楣墙」三段还原。 */
const WIN_SILL = 0.90
const WIN_TOP = 2.40

function WindowUnit({ win }) {
  const a = win.opening_m[0]
  const b = win.opening_m[1]
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const L = Math.hypot(dx, dy)
  const ux = dx / L
  const uy = dy / L
  const rotY = Math.atan2(-uy, ux)
  const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const midH = (WIN_SILL + WIN_TOP) / 2
  return (
    <group>
      {/* 窗台墙 */}
      <mesh position={[mid[0], WIN_SILL / 2, mid[1]]} rotation={[0, rotY, 0]} castShadow receiveShadow>
        <boxGeometry args={[L, WIN_SILL, WALL_T]} />
        <meshStandardMaterial color="#b3afa9" roughness={0.92} />
      </mesh>
      {/* 窗楣墙 */}
      <mesh position={[mid[0], (WIN_TOP + H_WALL) / 2, mid[1]]} rotation={[0, rotY, 0]} castShadow>
        <boxGeometry args={[L, H_WALL - WIN_TOP, WALL_T]} />
        <meshStandardMaterial color="#b3afa9" roughness={0.92} />
      </mesh>
      {/* 窗框 */}
      {[-1, 1].map((s) => (
        <mesh key={s} position={[mid[0] + ux * (L / 2) * s, midH, mid[1] + uy * (L / 2) * s]}
          rotation={[0, rotY, 0]}>
          <boxGeometry args={[0.05, WIN_TOP - WIN_SILL, WALL_T + 0.02]} />
          <meshStandardMaterial color="#b9bdc1" roughness={0.5} metalness={0.35} />
        </mesh>
      ))}
      {/* 玻璃 */}
      <mesh position={[mid[0], midH, mid[1]]} rotation={[0, rotY, 0]}>
        <boxGeometry args={[L - 0.06, WIN_TOP - WIN_SILL - 0.05, 0.02]} />
        <meshPhysicalMaterial color="#cfe9f2" transparent opacity={0.26} roughness={0.06}
          metalness={0} transmission={0.7} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

/* ---------- 飘窗：所属房间的一块 0.5m 抬高台面 ----------
   用户裁定：飘窗「与房间连通、只是台高 0.5m」，不是独立房间。
   所以 geom_v6 把飘窗面积并进所属房间多边形，并在 room.bays 里保留台面范围。
   这里把它渲染成高出地面 0.5m 的实体台（毛坯里的窗台板）。 */
const BAY_H = 0.50

function BayPlatform({ poly }) {
  const geom = useMemo(() => {
    const shape = shapeFrom(poly)
    return new THREE.ExtrudeGeometry(shape, {
      depth: BAY_H, bevelEnabled: false, curveSegments: 1,
    })
  }, [poly])
  return (
    <mesh geometry={geom} rotation={[-Math.PI / 2, 0, 0]} castShadow receiveShadow>
      <meshStandardMaterial color="#e7dfd0" roughness={0.95} />
    </mesh>
  )
}

/* ---------- 屋顶（漫游时盖顶） ---------- */
function Roof({ visible }) {
  const shape = useMemo(() => shapeFrom(roofData.polygon_m), [])
  if (!visible) return null
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, H_WALL + 0.02, 0]}>
      <shapeGeometry args={[shape]} />
      <meshStandardMaterial color="#f4f2ee" roughness={1} side={THREE.DoubleSide} />
    </mesh>
  )
}

/* ══════════════════════════════════════════════════════════════
   外部环境（17/26 层的高空语境）
   ──────────────────────────────────────────────────────────────
   屋子在 17 层，脚下 48m 才是地坪，四周是城市。原先把场景悬在虚空里，
   转到侧面看会"没有参照物"，高度感完全丢失。这里补三样东西：

     SkyDome    天空穹顶（顶点色渐变，零依赖，不用 shader）
     Ground     地坪 + 街道网格（尺度参照：每格 5m）
     Skyline    远景城市剪影（确定性伪随机，每次刷新完全一致）
     TowerShell 本楼体量：地面→本层 的楼身，以及本层→塔顶 的 9 层体量

   TowerShell 是"17/26"最直接的表达：半透明的楼身把套型托起来，
   一眼能看出"我们在这么高的位置"。俯视（图纸模式）时全部关闭，
   避免干扰正交判读。
   ══════════════════════════════════════════════════════════════ */

/* 顶点色天空穹顶。相比 drei 的 <Sky> 少一层依赖，且能做"地平线雾带"的效果。 */
function SkyDome({ cx, cy, radius = 1400 }) {
  const geo = useMemo(() => {
    const g = new THREE.SphereGeometry(radius, 32, 18)
    const pos = g.attributes.position
    const col = new Float32Array(pos.count * 3)
    const top = new THREE.Color('#2f6fc0')     // 天顶
    const mid = new THREE.Color('#a3c6e4')     // 中空
    const bot = new THREE.Color('#eef2f6')     // 地平线雾带
    for (let i = 0; i < pos.count; i++) {
      const t = THREE.MathUtils.clamp(pos.getY(i) / radius, -1, 1)
      const c = t >= 0
        ? mid.clone().lerp(top, Math.pow(t, 0.42))     // 指数小 -> 抬一点头就见到蓝
        : mid.clone().lerp(bot, Math.pow(-t, 0.45))
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b
    }
    g.setAttribute('color', new THREE.BufferAttribute(col, 3))
    return g
  }, [radius])
  return (
    <mesh geometry={geo} position={[cx, 0, cy]}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} fog={false} depthWrite={false} />
    </mesh>
  )
}

/* 地坪 + 街道网格：给"多高"一个可量测的参照（每格 5m）。 */
function Ground({ cx, cy }) {
  const S = 900
  return (
    <group position={[cx, GROUND_Y, cy]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[S, S]} />
        <meshStandardMaterial color="#8d9899" roughness={1} />
      </mesh>
      <gridHelper args={[S, S / 5, '#6f7a7c', '#7d888a']}
        position={[0, 0.06, 0]} material-transparent material-opacity={0.5} />
    </group>
  )
}

/* 确定性伪随机（mulberry32）：保证每次打开看到的是同一片城市，截图可复现。 */
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/* 远景城市剪影：环形撒点，避开正中的自家楼位。
   高度刻意压在自己这层（+48m 地坪以上）附近或以下 —— 否则几十栋比你还高的
   楼会把天空完全糊死；留出屋顶线与天空，高空感才出得来。 */
const SKYLINE = (() => {
  const rnd = mulberry32(20260919)
  const out = []
  // 近景一圈矮楼：把"楼下就是城市"填出来，避免大片空地显得像荒漠。
  // 必须放得够远（≥110m）—— 太近的话从本层俯看会正好糊在户型附近，喧宾夺主。
  for (let i = 0; i < 55; i++) {
    const ang = rnd() * Math.PI * 2
    const r = 110 + rnd() * 150
    out.push({ x: Math.cos(ang) * r, z: Math.sin(ang) * r,
               w: 15 + rnd() * 30, d: 15 + rnd() * 30,
               h: 5 + rnd() * 19, k: rnd() })
  }
  // 远景一圈：有高有矮，控制在"我这层"上下一带
  for (let i = 0; i < 110; i++) {
    const ang = rnd() * Math.PI * 2
    const r = 155 + rnd() * 420
    out.push({ x: Math.cos(ang) * r, z: Math.sin(ang) * r,
               w: 14 + rnd() * 30, d: 14 + rnd() * 30,
               h: 6 + Math.pow(rnd(), 2.0) * 58, k: rnd() })
  }
  return out
})()

function Skyline({ cx, cy }) {
  return (
    <group position={[cx, GROUND_Y, cy]}>
      {SKYLINE.map((b, i) => {
        const c = new THREE.Color().setHSL(0.58, 0.06 + b.k * 0.05, 0.52 + b.k * 0.16)
        return (
          <mesh key={i} position={[b.x, b.h / 2, b.z]} castShadow={false}>
            <boxGeometry args={[b.w, b.h, b.d]} />
            <meshStandardMaterial color={c} roughness={0.95} metalness={0}
              transparent opacity={0.92} />
          </mesh>
        )
      })}
    </group>
  )
}

/* 本楼体量：楼身（地坪→本层）与上部楼层（本层→塔顶），半透明不挡内部。 */
function TowerShell() {
  const shape = useMemo(() => shapeFrom(roofData.polygon_m), [])
  const below = useMemo(() => new THREE.ExtrudeGeometry(shape, {
    depth: -GROUND_Y, bevelEnabled: false, curveSegments: 1,
  }), [shape])
  const above = useMemo(() => new THREE.ExtrudeGeometry(shape, {
    depth: Math.max(0.1, TOWER_TOP_Y - H_WALL), bevelEnabled: false, curveSegments: 1,
  }), [shape])
  const mat = (op) => <meshStandardMaterial color="#cfc9c0" roughness={0.9}
    transparent opacity={op} depthWrite={false} side={THREE.DoubleSide} />
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <mesh geometry={below} position={[0, 0, GROUND_Y]}>
        {mat(0.16)}
      </mesh>
      <mesh geometry={above} position={[0, 0, H_WALL + 0.02]}>
        {mat(0.11)}
      </mesh>
    </group>
  )
}

/* 环境总装：仅第三人称 / 漫游时显示 */
function Surroundings({ ext, on }) {
  if (!on) return null
  return (
    <group>
      <SkyDome cx={ext.cx} cy={ext.cy} />
      <Ground cx={ext.cx} cy={ext.cy} />
      <Skyline cx={ext.cx} cy={ext.cy} />
      <TowerShell />
    </group>
  )
}

/* ---------- 俯视：正交相机（户型图式，无透视遮挡） ----------
   截图/演示用 URL 参数：
     ?zoom=3      放大倍数（默认 1 = 全屋）
     ?cx=&cy=     视图中心（米，默认取户型 bbox 中心）
     ?tilt=50     倾斜角（0=正俯视，>0 = 轴测，能看出 3D 高度） */
function TopView({ ext }) {
  const { size } = useThree()
  const q = useMemo(() => new URLSearchParams(window.location.search), [])
  const zoom = Math.abs(parseFloat(q.get('zoom') || '1')) || 1
  const tilt = parseFloat(q.get('tilt') || '0') || 0
  const cx = q.has('cx') ? parseFloat(q.get('cx')) : ext.cx
  const cy = q.has('cy') ? parseFloat(q.get('cy')) : ext.cy
  const aspect = size.width / Math.max(1, size.height)
  const halfH = Math.max(ext.h, ext.w / aspect) * 0.62 / zoom
  const halfW = halfH * aspect
  const rad = (tilt * Math.PI) / 180
  const dist = 60
  return (
    <>
      <OrthographicCamera makeDefault
        position={[cx, dist * Math.cos(rad), cy + dist * Math.sin(rad) + 0.001]}
        left={-halfW} right={halfW} top={halfH} bottom={-halfH}
        near={0.1} far={300} />
      <OrbitControls target={[cx, 0, cy]} enablePan enableZoom
        enableRotate={false} />
    </>
  )
}

/* ---------- 第三人称环视（默认视角） ----------
   一个可以绕着屋子转的透视轨道相机：拖动旋转、滚轮缩放、右键平移。
   相比正交俯视，它保留透视与高度，能真正"看"出这是间 3D 房子。

   URL 参数（便于分享/自动截图）：
     ?mode=orbit            进入本视角（也是默认）
     ?az=25                 方位角（度）。0 = 从南侧看（+z），逆时针为正
     ?el=20                 仰角（度）。90 = 正俯视；默认压得较低，好把
                            天空与远景城市一起收进画面（高仰角会只剩地面）
     ?dist=1.5              取景距离系数 */
function OrbitView({ ext }) {
  const q = useMemo(() => new URLSearchParams(window.location.search), [])
  const num = (k, d) => (q.has(k) ? parseFloat(q.get(k)) : d)
  const az = num('az', 25)
  const el = Math.max(4, Math.min(84, num('el', 14)))
  const distK = Math.abs(num('dist', 1.55)) || 1.55
  const R = Math.max(ext.w, ext.h) * 1.25 * distK
  const elr = (el * Math.PI) / 180
  const azr = (az * Math.PI) / 180
  const pos = [
    ext.cx + R * Math.cos(elr) * Math.sin(azr),
    R * Math.sin(elr),
    ext.cy + R * Math.cos(elr) * Math.cos(azr),
  ]
  return (
    <>
      <PerspectiveCamera makeDefault position={pos} fov={45} near={0.1} far={6000} />
      <OrbitControls makeDefault target={[ext.cx, 2.0, ext.cy]}
        enablePan enableZoom enableRotate
        enableDamping dampingFactor={0.08}
        minDistance={2.5} maxDistance={Math.max(420, R * 4)}
        maxPolarAngle={Math.PI / 2 - 0.015} />
    </>
  )
}

/* ---------- 第一人称 WASD ---------- */
function FPSMove() {
  const { camera } = useThree()
  const keys = useRef({})
  useEffect(() => {
    const d = (e) => { keys.current[e.code] = true }
    const u = (e) => { keys.current[e.code] = false }
    window.addEventListener('keydown', d); window.addEventListener('keyup', u)
    return () => { window.removeEventListener('keydown', d); window.removeEventListener('keyup', u) }
  }, [])
  useFrame((_, dt) => {
    const f = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion); f.y = 0; f.normalize()
    const r = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion); r.y = 0; r.normalize()
    const mv = new THREE.Vector3()
    if (keys.current.KeyW) mv.add(f)
    if (keys.current.KeyS) mv.sub(f)
    if (keys.current.KeyA) mv.sub(r)
    if (keys.current.KeyD) mv.add(r)
    if (mv.lengthSq() > 0) {
      mv.normalize().multiplyScalar(SPEED * dt)
      camera.position.add(mv)
      camera.position.y = EYE
    }
  })
  return null
}

/* ---------- 主光 ----------
   原先 directionalLight 的 target 默认在**世界原点**，而本套型中心在
   (ext.cx, ext.cy) ≈ (12.2, 9.3) —— 阴影正交框（±14）因此偏掉了大半，
   房间里的影子被裁。这里把 target 挪到套型中心，并按套型尺寸给足范围。 */
function SunLight({ cx, cy, castShadow }) {
  const ref = useRef()
  useEffect(() => {
    const l = ref.current
    if (!l) return
    l.target.position.set(cx, 0, cy)
    l.target.updateMatrixWorld()          // getWorldPosition 会再刷一次，双保险
  }, [cx, cy])
  return (
    <directionalLight ref={ref} position={[cx + 16, 34, cy + 13]} intensity={1.05}
      castShadow={castShadow}
      shadow-mapSize-width={2048} shadow-mapSize-height={2048}
      shadow-camera-left={-15} shadow-camera-right={15}
      shadow-camera-top={15} shadow-camera-bottom={-15}
      shadow-camera-near={1} shadow-camera-far={160}
      shadow-bias={-0.0006} />
  )
}

/* ---------- 场景 ---------- */
export default function App() {
  // 默认「第三人称环视」。?mode=orbit|top|walk 可显式指定。
  // 兼容旧链接/旧截图脚本：只带 ?tilt= / ?zoom= / ?cx= / ?cy= 的一律按正交俯视处理。
  const [mode, setMode] = useState(() => {
    const q = new URLSearchParams(window.location.search)
    const m = q.get('mode')
    if (m === 'top' || m === 'walk' || m === 'orbit') return m
    if (q.has('tilt') || q.has('zoom') || q.has('cx') || q.has('cy')) return 'top'
    return 'orbit'
  })
  // 外部环境只在"有空域"的两个视角里出现；正交俯视是图纸模式，要干净。
  const envOn = mode === 'orbit' || mode === 'walk'
  // 诊断开关：?debug=wall | door | floor —— 用于判定渲染瑕疵归属哪个 mesh
  const debug = useMemo(
    () => new URLSearchParams(window.location.search).get('debug'), [])
  const showWall = !debug || debug === 'wall'
  const showDoor = !debug || debug === 'door'
  const showFloor = !debug || debug === 'floor'

  const rooms = graph.rooms
  const roomNameOf = useMemo(() => {
    const m = {}
    for (const r of rooms) m[r.id] = r.name
    return (id) => (id ? m[id] : null)
  }, [rooms])

  const ext = useMemo(() => {
    let mnx = 1e9, mny = 1e9, mxx = -1e9, mxy = -1e9
    for (const w of wallsPoly) for (const p of w.shell) {
      mnx = Math.min(mnx, p[0]); mny = Math.min(mny, p[1])
      mxx = Math.max(mxx, p[0]); mxy = Math.max(mxy, p[1])
    }
    return { cx: (mnx + mxx) / 2, cy: (mny + mxy) / 2, w: mxx - mnx, h: mxy - mny }
  }, [])
  const topDist = Math.max(ext.w, ext.h) * 1.55

  // 漫游初始站位：面积最大房间（LDK）的质心稍偏南，面朝北（-z）——
  // 一眼能看到厨房、公卫、书房与厨房阳台的玻璃移门。
  // 早先直接取墙 bbox 中心，常贴着墙或站在墙体里。
  const walkStart = useMemo(() => {
    if (!rooms.length) return [ext.cx, EYE, ext.cy]
    const main = [...rooms].sort((a, b) => b.area_m2 - a.area_m2)[0]
    const p = main.polygon_m
    const cx = p.reduce((s, q) => s + q[0], 0) / p.length
    const cy = p.reduce((s, q) => s + q[1], 0) / p.length
    return [cx, EYE, cy + 2.0]
  }, [rooms, ext])

  const swing = graph.doors.filter((d) => d.type === 'swing').length
  const sliding = graph.doors.filter((d) => d.type === 'sliding').length
  const nWin = (graph.windows || []).length

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(graph, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'room-graph.json'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', background: '#cfe3f2' }}>
      <div style={{
        position: 'absolute', top: 12, left: 12, zIndex: 10, background: 'rgba(20,24,28,0.72)',
        color: '#fff', padding: '12px 14px', borderRadius: 8, fontFamily: 'system-ui, sans-serif',
        fontSize: 13, lineHeight: 1.7, backdropFilter: 'blur(4px)', minWidth: 220,
      }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>春晓户型 · 3D 毛坯房</div>
        <div>房间 {rooms.length} · 门 {graph.doors.length}（平开 {swing} / 玻璃移门 {sliding}）</div>
        <div>窗 {nWin} · 墙段 {wallsPoly.length} · 套内 {graph.checks.area_total_m2} m²</div>
        <div style={{ color: '#8fd6a8' }}>
          楼层 {FLOOR_NO}/{FLOOR_TOTAL} · 室外地坪 −{Math.abs(GROUND_Y)} m
        </div>
        <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {[['orbit', '第三人称环视'], ['top', '正交俯视'], ['walk', '第一人称']].map(([m, label]) => (
            <button key={m} onClick={() => setMode(m)} style={{
              padding: '5px 9px', borderRadius: 5, cursor: 'pointer', font: 'inherit',
              border: mode === m ? '1px solid #7fb2ff' : '1px solid rgba(255,255,255,0.18)',
              background: mode === m ? 'rgba(127,178,255,0.30)' : 'rgba(255,255,255,0.08)',
              color: '#fff',
            }}>{label}</button>
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          <button onClick={exportJson} style={{ padding: '5px 9px' }}>导出 JSON</button>
        </div>
        <div style={{ marginTop: 6, fontSize: 12, color: '#bcd', maxWidth: 250 }}>
          {mode === 'orbit' && '拖动旋转 · 滚轮缩放 · 右键平移（外部环境已渲染）'}
          {mode === 'walk' && '点击画面锁定 · WASD 行走 · ESC 释放'}
          {mode === 'top' && '正交图纸视角 · 滚轮缩放 · 右键平移'}
        </div>
      </div>

      <Canvas shadows dpr={[1, 2]}>
        {envOn
          ? <fog attach="fog" args={['#e3eaf2', 70, 700]} />   // 与穹顶地平线色对齐，让地平线化进雾里
          : <color attach="background" args={['#cfe3f2']} />}
        <hemisphereLight args={['#ffffff', '#c8c2b8', envOn ? 0.78 : 0.62]} />
        <SunLight cx={ext.cx} cy={ext.cy} castShadow={mode !== 'top'} />
        <ambientLight intensity={envOn ? 0.40 : 0.5} />

        {mode === 'top' && <TopView ext={ext} />}
        {mode === 'orbit' && <OrbitView ext={ext} />}
        {mode === 'walk' && (
          <>
            <PerspectiveCamera makeDefault position={walkStart} fov={68} />
            <PointerLockControls />
            <FPSMove />
          </>
        )}

        {showFloor && rooms.map((r) => <RoomFloor key={r.id} poly={r.polygon_m} name={r.name} />)}
        {showFloor && rooms.flatMap((r) => (r.bays || []).map((b, i) => (
          <BayPlatform key={`${r.id}-bay${i}`} poly={b} />
        )))}
        {showWall && wallsPoly.map((w, i) => (
          <WallBand key={i} poly={w} tri={wallsTri.bands[i]} />
        ))}
        {showDoor && graph.doors.map((d) => <DoorUnit key={d.id} door={d} roomNameOf={roomNameOf} />)}
        {showDoor && (graph.windows || []).map((w) => <WindowUnit key={w.id} win={w} />)}
        <Surroundings ext={ext} on={envOn} />
        <Roof visible={mode === 'walk'} />
      </Canvas>
    </div>
  )
}
