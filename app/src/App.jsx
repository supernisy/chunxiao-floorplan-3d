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

/* 按房间名归类面层。本图房间名自带用途（主卫/次卫/公卫/客厅阳台/瑶瑶衣帽间…），
   直接按关键字判，比再引入一个 type 字段更省事、也不会与管线口径打架。

   ⚠️ LDK 是**合并房间**（客厅+餐厅+厨房共 52.61 m²）：厨房区在几何上切不出来，
      故整间按木地板处理 —— 宁可不切，也好过切歪。 */
function floorKind(name) {
  const n = name || ''
  if (n.includes('阳台') || n.includes('卫')) return 'tile'
  if (n.includes('电梯') || n.includes('楼梯')) return 'concrete'
  return 'wood'
}

/* 程序化面层纹理（canvas 现画，零外部图片资源 —— 单文件离线版不打折）。
   tiling 尺寸刻意取砖/板宽的整数倍，平铺时才不会出现半块砖、错位缝：
     wood  canvas 代表 3.2 m²，16 条 × 0.2 m 板宽
     tile  canvas 代表 2.4 m²，4×4 块 × 0.6 m 方砖 */
const FLOOR_TILE_M = { wood: 3.2, tile: 2.4 }
const _floorTex = {}

function floorTexture(kind) {
  if (_floorTex[kind]) return _floorTex[kind]
  const S = 1024
  const cv = document.createElement('canvas')
  cv.width = cv.height = S
  const g = cv.getContext('2d')
  const rnd = mulberry32(kind === 'wood' ? 7788 : 4242)

  if (kind === 'wood') {
    const rows = 16
    const h = S / rows
    for (let i = 0; i < rows; i++) {
      const y = i * h
      // 每条板底色轻微扰动，避免整片死平
      g.fillStyle = `hsl(31, 30%, ${Math.round((0.66 + rnd() * 0.14) * 100)}%)`
      g.fillRect(0, y, S, h)
      // 木纹细线
      g.strokeStyle = 'rgba(112,76,38,0.13)'
      g.lineWidth = 1
      for (let k = 0; k < 6; k++) {
        const yy = y + h * (0.12 + 0.76 * rnd())
        g.beginPath(); g.moveTo(0, yy); g.lineTo(S, yy); g.stroke()
      }
      // 板间横缝
      g.fillStyle = 'rgba(86,56,28,0.50)'
      g.fillRect(0, y, S, 2)
      // 每条板的端头竖缝（错缝铺法）
      for (let x = rnd() * S * 0.5; x < S; x += S * (0.34 + rnd() * 0.42)) {
        g.fillRect(x, y, 2, h)
      }
    }
  } else {
    const n = 4
    const c = S / n
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      g.fillStyle = `hsl(198, 7%, ${Math.round((0.87 + rnd() * 0.07) * 100)}%)`
      g.fillRect(j * c, i * c, c, c)
    }
    g.strokeStyle = 'rgba(146,154,158,0.85)'
    g.lineWidth = 3
    for (let i = 0; i <= n; i++) {
      g.beginPath(); g.moveTo(i * c, 0); g.lineTo(i * c, S); g.stroke()
      g.beginPath(); g.moveTo(0, i * c); g.lineTo(S, i * c); g.stroke()
    }
  }

  const t = new THREE.CanvasTexture(cv)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  _floorTex[kind] = t
  return t
}

function RoomFloor({ poly, name }) {
  const kind = floorKind(name)
  const geom = useMemo(() => {
    const g = new THREE.ShapeGeometry(shapeFrom(poly))
    if (kind !== 'concrete' && g.attributes.uv) {
      // 用**世界米数**当 UV：各房间砖/板尺寸才一致，相邻房间的地板"接得上"。
      // （ShapeGeometry 默认 UV 是按轮廓参数走的，直接贴图会大小不一。）
      const pos = g.attributes.position
      const uv = new Float32Array(pos.count * 2)
      const T = FLOOR_TILE_M[kind]
      for (let i = 0; i < pos.count; i++) {
        uv[i * 2] = pos.getX(i) / T
        uv[i * 2 + 1] = pos.getY(i) / T
      }
      g.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
    }
    return g
  }, [poly, kind])

  return (
    <mesh geometry={geom} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]} receiveShadow>
      {kind === 'concrete'
        ? <meshStandardMaterial color={tint(name)} roughness={0.98} metalness={0} />
        : <meshStandardMaterial map={floorTexture(kind)}
            roughness={kind === 'wood' ? 0.70 : 0.34}
            metalness={kind === 'wood' ? 0 : 0.03} />}
    </mesh>
  )
}

/* ---------- 房间名 / 面积标注 ----------
   认房间靠肉眼比色太费劲，每间挂一块「房名 + 面积」牌。

   技术选择：**canvas 画中文 → CanvasTexture → sprite**。
   不用 drei 的 <Text>：它底层是 troika，默认只打包拉丁字体，中文会整片缺字形；
   而内联一份中文字体动辄好几 MB，单文件离线版会被撑爆。canvas 直接吃系统字体，
   零依赖、零体积，离线与联机表现一致。

   用 sprite（billboard）而非贴地平面：任何视角都正对相机，斜看也读得清。 */
const LABEL_CACHE = {}

function labelTexture(name, area) {
  const key = `${name}|${area}`
  if (LABEL_CACHE[key]) return LABEL_CACHE[key]
  const W = 512, H = 168
  const cv = document.createElement('canvas')
  cv.width = W; cv.height = H
  const g = cv.getContext('2d')
  const rr = (x, y, w, h, r) => {
    g.beginPath()
    g.moveTo(x + r, y)
    g.arcTo(x + w, y, x + w, y + h, r)
    g.arcTo(x + w, y + h, x, y + h, r)
    g.arcTo(x, y + h, x, y, r)
    g.arcTo(x, y, x + w, y, r)
    g.closePath()
  }
  // 深色半透明底板：在浅色地板、白色瓷砖上都读得清
  g.fillStyle = 'rgba(26,30,34,0.66)'
  rr(4, 4, W - 8, H - 8, 26); g.fill()
  g.strokeStyle = 'rgba(255,255,255,0.28)'; g.lineWidth = 3
  rr(4, 4, W - 8, H - 8, 26); g.stroke()

  const CJK = '"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Noto Sans CJK SC",sans-serif'
  g.textAlign = 'center'; g.textBaseline = 'middle'
  g.fillStyle = '#ffffff'
  g.font = `bold 64px ${CJK}`
  g.fillText(name, W / 2, 62)
  g.fillStyle = '#ffd98a'
  g.font = `46px ${CJK}`
  g.fillText(`${area} m²`, W / 2, 124)

  const t = new THREE.CanvasTexture(cv)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  LABEL_CACHE[key] = t
  return t
}

/* 多边形**面积加权质心**（对 L 形 / 凹多边形比"顶点平均"稳得多，
   顶点平均会被密集顶点那一侧拽偏）。 */
function polyCentroid(poly) {
  let a = 0, cx = 0, cy = 0
  for (let i = 0; i < poly.length; i++) {
    const [x0, y0] = poly[i]
    const [x1, y1] = poly[(i + 1) % poly.length]
    const f = x0 * y1 - x1 * y0
    a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
  }
  a *= 0.5
  if (Math.abs(a) < 1e-9) return poly[0]
  return [cx / (6 * a), cy / (6 * a)]
}

function pointInPoly(x, y, poly) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1]
    const xj = poly[j][0], yj = poly[j][1]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

/* 锚点：质心 → bbox 中心 → 首个顶点（逐级回退）。
   公卫是 L 形，凹多边形的质心偶尔会落在轮廓外，必须校验。 */
function labelAnchor(poly) {
  const c = polyCentroid(poly)
  if (pointInPoly(c[0], c[1], poly)) return c
  let mnx = 1e9, mny = 1e9, mxx = -1e9, mxy = -1e9
  for (const p of poly) {
    mnx = Math.min(mnx, p[0]); mny = Math.min(mny, p[1])
    mxx = Math.max(mxx, p[0]); mxy = Math.max(mxy, p[1])
  }
  const b = [(mnx + mxx) / 2, (mny + mxy) / 2]
  return pointInPoly(b[0], b[1], poly) ? b : poly[0]
}

/* sprite 是 billboard：永远正对相机，文字上下由相机 up 决定 ——
   环视与正交俯视两种视角都试拍过，无需额外翻转。

   尺寸两重自适应：
   ① **按房间面积**缩（小房间挂大牌子会盖住邻间）——2.24㎡ 的公卫与 52.61㎡ 的
      LDK 用同一尺寸，俯视图里前者会糊到隔壁去；
   ② **按视角**缩 —— 环视是透视，标签会被投影挤向画面中央，比正交俯视更需要收敛。 */
function RoomLabel({ poly, name, area, mode }) {
  const tex = useMemo(() => labelTexture(name, area), [name, area])
  const a = useMemo(() => labelAnchor(poly), [poly])
  const top = mode === 'top'
  const k = Math.min(1, Math.max(0.56, Math.pow(area / 18, 0.26)))
  const w = (top ? 2.05 : 1.58) * k
  return (
    <sprite position={[a[0], top ? 0.78 : 1.55, a[1]]} scale={[w, w * 0.328, 1]} renderOrder={20}>
      <spriteMaterial map={tex} transparent depthTest={false} depthWrite={false}
        toneMapped={false} />
    </sprite>
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

/* 地坪 + 两级街道网格：给"多高"一个可量测的参照。
   5m 细格读尺度，50m 粗格当"主干道"——单一一层网格从 48m 高看会糊成一张纸。

   ⚠️ 地坪**不接收阴影**（故意不加 `receiveShadow`）：太阳的阴影正交框只有 ±15，
   而户型的影子被 48m 的高差甩到五六十米外的地面上，早已出框 —— 采样 UV 被 clamp，
   远处地上会留下一块边缘生硬的"影块"，看着像凭空多了一截墙。 */
function Ground({ cx, cy }) {
  const S = 900
  return (
    <group position={[cx, GROUND_Y, cy]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[S, S]} />
        <meshStandardMaterial color="#78838a" roughness={1} />
      </mesh>
      <gridHelper args={[S, S / 5, '#66727a', '#727e86']}
        position={[0, 0.06, 0]} material-transparent material-opacity={0.45} />
      <gridHelper args={[S, S / 50, '#4f5a61', '#4f5a61']}
        position={[0, 0.12, 0]} material-transparent material-opacity={0.60} />
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
   楼会把天空完全糊死；留出屋顶线与天空，高空感才出得来。

   ⚠️ 剪影**不做半透明**：原先 `transparent opacity=0.92` + 高亮度 HSL（L 0.52~0.68）
   会让 165 栋楼互相叠加、又与天空混色，远看是一坨惨白的浮板。
   改为不透明 + 压低明度、拉开饱和度后，楼与楼之间才有前后层次。 */
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
        const c = new THREE.Color().setHSL(0.60, 0.13 + b.k * 0.10, 0.35 + b.k * 0.20)
        return (
          <mesh key={i} position={[b.x, b.h / 2, b.z]} castShadow={false}>
            <boxGeometry args={[b.w, b.h, b.d]} />
            <meshStandardMaterial color={c} roughness={0.95} metalness={0} />
          </mesh>
        )
      })}
    </group>
  )
}

/* 本层以上的 (26-17)=9 层：**不画半透明体**。
   原先 above 用 ExtrudeGeometry + opacity 0.11 + depthWrite:false + DoubleSide，
   斜看时前/后侧壁与顶面反复叠加，而挤出体的分段边界又让叠加层数跳变 ——
   画面顶部就出现一片"竖条纹幕布"，把天空糊掉。
   改为「每层一条水平环线 + 四角竖棱」：既明确读出"楼上还有 9 层"，
   又几乎不占像素，天空与远景得以透出来。 */
function FloorRings() {
  const geo = useMemo(() => {
    const poly = roofData.polygon_m
    const seg = []
    const put = (a, y, b) => seg.push(a[0], y, a[1], b[0], y, b[1])
    // 每标准层楼面高度画一条闭合环线
    const nAbove = Math.max(0, FLOOR_TOTAL - FLOOR_NO)
    for (let f = 1; f <= nAbove; f++) {
      const y = H_WALL + f * H_FLOOR
      if (y > TOWER_TOP_Y + 1e-6) break
      for (let i = 0; i < poly.length; i++) put(poly[i], y, poly[(i + 1) % poly.length])
    }
    // 四角竖棱：把层层环线串成一个体量，避免看起来像"飘着的相框"
    let mnx = 1e9, mny = 1e9, mxx = -1e9, mxy = -1e9
    for (const p of poly) {
      mnx = Math.min(mnx, p[0]); mny = Math.min(mny, p[1])
      mxx = Math.max(mxx, p[0]); mxy = Math.max(mxy, p[1])
    }
    for (const [x, z] of [[mnx, mny], [mxx, mny], [mxx, mxy], [mnx, mxy]]) {
      seg.push(x, H_WALL, z, x, TOWER_TOP_Y, z)
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3))
    return g
  }, [])
  return (
    <lineSegments geometry={geo}>
      <lineBasicMaterial color="#ded8ce" transparent opacity={0.40}
        depthWrite={false} toneMapped={false} />
    </lineSegments>
  )
}

/* 本楼体量：楼身（地坪→本层，极淡的半透明壳）＋ 本层以上的楼层环线。
   ⚠️ 楼身三个参数都是踩过坑的：
   - `opacity` 必须够低（0.20 时是一根抢眼的"纱柱"，把地面挡没了）；
   - 不能 `DoubleSide`：前后两个侧壁叠加会让纱幕感翻倍；
   - 底面要**离地坪 0.1m**：否则挤出体底面与 Ground 平面共面 → z-fighting 锯齿。 */
function TowerShell() {
  const shape = useMemo(() => shapeFrom(roofData.polygon_m), [])
  const below = useMemo(() => new THREE.ExtrudeGeometry(shape, {
    depth: -GROUND_Y - 0.1, bevelEnabled: false, curveSegments: 1,
  }), [shape])
  return (
    <group>
      <group rotation={[-Math.PI / 2, 0, 0]}>
        <mesh geometry={below} position={[0, 0, GROUND_Y + 0.1]}>
          <meshStandardMaterial color="#c6c0b6" roughness={0.9}
            transparent opacity={0.11} depthWrite={false} />
        </mesh>
      </group>
      <FloorRings />
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
     ?el=36                 仰角（度）。90 = 正俯视。
                            第 13 轮实测后由 14 提到 36：14° 时视线被 2.9m 的墙完全
                            挡住，**室内地面根本看不见**（地面分区材质等于白做）；
                            36° 能同时看清室内地面与远景城市，是两者的平衡点。
                            三档对比见 `data/v6/cmp_angles.png`（28/36/44），
                            44° 已经把天空吃掉，故取 36。
     ?dist=1.10             取景距离系数 */
function OrbitView({ ext }) {
  const q = useMemo(() => new URLSearchParams(window.location.search), [])
  const num = (k, d) => (q.has(k) ? parseFloat(q.get(k)) : d)
  const az = num('az', 25)
  const el = Math.max(4, Math.min(84, num('el', 36)))
  const distK = Math.abs(num('dist', 1.10)) || 1.10
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

  // 房间标注：默认开，?labels=0 关。第一人称贴地行走时强制关
  // （牌子挂在 0.78m 高，正常视高 1.62m 会糊在脸上挡路）。
  const [labels, setLabels] = useState(
    () => new URLSearchParams(window.location.search).get('labels') !== '0')
  const labelsOn = labels && mode !== 'walk'
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
        <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button onClick={exportJson} style={{ padding: '5px 9px' }}>导出 JSON</button>
          <button onClick={() => setLabels((v) => !v)} style={{
            padding: '5px 9px', borderRadius: 5, cursor: 'pointer', font: 'inherit',
            border: labels ? '1px solid #7fb2ff' : '1px solid rgba(255,255,255,0.18)',
            background: labels ? 'rgba(127,178,255,0.30)' : 'rgba(255,255,255,0.08)',
            color: '#fff',
          }}>房间标注 {labels ? '开' : '关'}</button>
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
        <hemisphereLight args={['#ffffff', '#c8c2b8', envOn ? 0.68 : 0.62]} />
        <SunLight cx={ext.cx} cy={ext.cy} castShadow={mode !== 'top'} />
        <ambientLight intensity={envOn ? 0.30 : 0.5} />

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
        {labelsOn && rooms.map((r) => (
          <RoomLabel key={`lbl-${r.id}`} poly={r.polygon_m} name={r.name}
            area={r.area_m2} mode={mode} />
        ))}
        <Surroundings ext={ext} on={envOn} />
        <Roof visible={mode === 'walk'} />
      </Canvas>
    </div>
  )
}
