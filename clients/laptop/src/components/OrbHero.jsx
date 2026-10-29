import { useRef, useEffect, useMemo } from 'react'

// Holographic data-globe, canvas-rendered: points distributed on a unit
// sphere (Fibonacci sphere for even coverage), connected to their nearest
// neighbors to form a wireframe mesh, rotated in real 3D with perspective
// projection each frame, additive ("lighter") blending for the glow/bloom
// look. This is a genuinely different technique from the earlier SVG
// attempts — real depth and density instead of a handful of flat lines.
const STATE_CFG = {
  idle: { color: [90, 170, 255], core: [214, 240, 255], speed: 0.45, pulse: 2.4 },
  thinking: { color: [110, 200, 255], core: [230, 250, 255], speed: 0.85, pulse: 1.1 },
  working: { color: [130, 210, 255], core: [200, 240, 255], speed: 1.1, pulse: 0.7 },
  streaming: { color: [150, 225, 255], core: [255, 255, 255], speed: 1.25, pulse: 0.55 },
  disconnected: { color: [70, 75, 90], core: [110, 115, 130], speed: 0.12, pulse: 4 },
}

const POINT_COUNT = 190
const SPARK_COUNT = 26
const NEIGHBOR_DIST = 0.26 // unit-sphere distance threshold for mesh edges
const CAMERA_D = 2.3
const TILT = 0.35 // static camera tilt (radians) for an angled view

function fibonacciSphere(n) {
  const pts = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = golden * i
    pts.push([Math.cos(theta) * r, y, Math.sin(theta) * r])
  }
  return pts
}

function buildGeometry() {
  const sphere = fibonacciSphere(POINT_COUNT)

  // precompute mesh edges: connect each point to its nearest few neighbors
  const edges = []
  for (let i = 0; i < sphere.length; i++) {
    const dists = []
    for (let j = 0; j < sphere.length; j++) {
      if (i === j) continue
      const [ax, ay, az] = sphere[i]
      const [bx, by, bz] = sphere[j]
      const d = Math.hypot(ax - bx, ay - by, az - bz)
      if (d < NEIGHBOR_DIST) dists.push([d, j])
    }
    dists.sort((a, b) => a[0] - b[0])
    for (const [, j] of dists.slice(0, 2)) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`
      edges.push({ key, a: i, b: j })
    }
  }
  const seen = new Set()
  const uniqueEdges = edges.filter(e => (seen.has(e.key) ? false : (seen.add(e.key), true)))

  // sparks: short stray lines poking past the sphere silhouette, anchored
  // to a random existing point — matches the reference's jagged overshoot.
  const rand = mulberry32(99)
  const sparks = []
  for (let i = 0; i < SPARK_COUNT; i++) {
    const base = sphere[Math.floor(rand() * sphere.length)]
    const [bx, by, bz] = base
    const len = 1 + rand() * 0.35
    sparks.push({ from: base, to: [bx * len, by * len, bz * len] })
  }

  return { sphere, edges: uniqueEdges, sparks }
}

function mulberry32(seed) {
  let a = seed
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function rotateY(p, a) {
  const [x, y, z] = p
  const c = Math.cos(a), s = Math.sin(a)
  return [x * c + z * s, y, -x * s + z * c]
}
function rotateX(p, a) {
  const [x, y, z] = p
  const c = Math.cos(a), s = Math.sin(a)
  return [x, y * c - z * s, y * s + z * c]
}

// Synthetic speech envelope, calibrated against real audio: synthesized three
// sample lines with the actual configured voice (Kokoro "af_heart") and
// measured the RMS envelope. Real syllable-peak rate came out to 5.3-5.5 Hz
// (vs. the ~4.4 Hz naive WPM-based estimate). Verified live (Playwright
// attached to the running window via CDP) that an earlier version of this —
// two independently power-curved terms multiplied together — compounds down
// to a typically tiny product (observed peak scale 1.023 instead of the
// intended ~1.2), since multiplying two sub-1 fractions crushes the result.
// Fixed: the syllable term uses a gentler power curve so it actually spans
// most of its range, and the phrase-level pause is a gate (mostly fully open,
// only attenuating near the bottom of its own slow cycle) instead of a second
// continuously-multiplying power curve.
function speechEnvelope(t) {
  const a = Math.sin(t * 2 * Math.PI * 5.4) * 0.5 + 0.5
  const b = Math.sin(t * 2 * Math.PI * 7.1 + 1.3) * 0.5 + 0.5
  const c = Math.sin(t * 2 * Math.PI * 3.8 + 2.1) * 0.5 + 0.5
  const syllable = Math.pow(a * 0.5 + b * 0.3 + c * 0.2, 1.6)

  const phraseRaw = Math.sin(t * 2 * Math.PI * 0.45 + 0.5) * 0.5 + 0.5
  const gate = phraseRaw < 0.25 ? phraseRaw / 0.25 : 1

  return syllable * gate
}

export default function OrbHero({ orbState, size = 128 }) {
  const canvasRef = useRef(null)
  const wrapperRef = useRef(null)
  const geometry = useMemo(buildGeometry, [])
  const cfgRef = useRef(STATE_CFG[orbState] ?? STATE_CFG.idle)
  cfgRef.current = STATE_CFG[orbState] ?? STATE_CFG.idle
  const orbStateRef = useRef(orbState)
  orbStateRef.current = orbState

  useEffect(() => {
    // Reset to resting scale whenever we leave the talking state, so it
    // doesn't get stuck mid-pulse — CSS transition eases this one smoothly,
    // unlike the snappy per-frame updates applied while actually talking.
    if (orbState !== 'streaming' && wrapperRef.current) {
      wrapperRef.current.style.transform = 'scale(1)'
    }
  }, [orbState])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = size * dpr
    canvas.height = size * dpr
    ctx.scale(dpr, dpr)

    const cx = size / 2, cy = size / 2
    const R = size * 0.34
    let angle = 0
    let raf

    const project = ([x, y, z]) => {
      const scale = CAMERA_D / (CAMERA_D - z)
      return [cx + x * R * scale, cy + y * R * scale, z, scale]
    }

    const draw = () => {
      const cfg = cfgRef.current
      angle += 0.006 * cfg.speed

      if (orbStateRef.current === 'streaming' && wrapperRef.current) {
        const env = speechEnvelope(performance.now() / 1000)
        wrapperRef.current.style.transform = `scale(${1 + env * 0.35})`
      }

      const rotated = geometry.sphere.map(p => rotateX(rotateY(p, angle), TILT))
      const projected = rotated.map(project)

      ctx.clearRect(0, 0, size, size)
      ctx.globalCompositeOperation = 'lighter'

      const [r, g, b] = cfg.color

      // mesh edges
      for (const e of geometry.edges) {
        const pa = projected[e.a], pb = projected[e.b]
        const depth = (rotated[e.a][2] + rotated[e.b][2]) / 2
        const alpha = 0.08 + Math.max(0, (depth + 1) / 2) * 0.35
        ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`
        ctx.lineWidth = 0.6
        ctx.beginPath()
        ctx.moveTo(pa[0], pa[1])
        ctx.lineTo(pb[0], pb[1])
        ctx.stroke()
      }

      // sparks (jagged overshoot lines)
      for (const s of geometry.sparks) {
        const pa = project(rotateX(rotateY(s.from, angle), TILT))
        const pb = project(rotateX(rotateY(s.to, angle), TILT))
        ctx.strokeStyle = `rgba(${r},${g},${b},0.5)`
        ctx.lineWidth = 0.8
        ctx.beginPath()
        ctx.moveTo(pa[0], pa[1])
        ctx.lineTo(pb[0], pb[1])
        ctx.stroke()
      }

      // points
      for (let i = 0; i < projected.length; i++) {
        const [px, py, z] = projected[i]
        const alpha = 0.15 + Math.max(0, (z + 1) / 2) * 0.7
        const rad = 0.5 + Math.max(0, (z + 1) / 2) * 0.9
        ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`
        ctx.beginPath()
        ctx.arc(px, py, rad, 0, Math.PI * 2)
        ctx.fill()
      }

      // radiating spokes from center
      ctx.strokeStyle = `rgba(${r},${g},${b},0.25)`
      ctx.lineWidth = 0.6
      for (let i = 0; i < 10; i++) {
        const a = angle * 0.3 + (i / 10) * Math.PI * 2
        ctx.beginPath()
        ctx.moveTo(cx, cy)
        ctx.lineTo(cx + Math.cos(a) * R * 1.15, cy + Math.sin(a) * R * 0.5 * 1.15)
        ctx.stroke()
      }

      // bright core
      const [cr, cg, cb] = cfg.core
      const pulse = 0.75 + Math.sin(performance.now() / (cfg.pulse * 300)) * 0.25
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.3)
      grad.addColorStop(0, `rgba(${cr},${cg},${cb},${pulse})`)
      grad.addColorStop(0.6, `rgba(${r},${g},${b},${pulse * 0.5})`)
      grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
      ctx.fillStyle = grad
      ctx.beginPath()
      ctx.arc(cx, cy, R * 0.3, 0, Math.PI * 2)
      ctx.fill()

      ctx.globalCompositeOperation = 'source-over'
      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [size, geometry])

  return (
    <div
      ref={wrapperRef}
      id="orb-wrapper"
      className="shrink-0"
      style={{
        width: size,
        height: size,
        opacity: orbState === 'disconnected' ? 0.5 : 1,
        // transform is deliberately NOT set here — it's owned entirely by
        // the imperative code below (the rAF loop while streaming, the
        // reset effect otherwise). Declaring it in JSX would make every
        // re-render (which happens on every token while streaming, since
        // the parent updates message state per-token) stomp the DOM mutation
        // right back to whatever this object says, fighting the animation.
        transition: 'opacity 0.7s ease, transform 0.12s ease-out',
      }}
    >
      <canvas ref={canvasRef} style={{ width: size, height: size, display: 'block' }} />
    </div>
  )
}
