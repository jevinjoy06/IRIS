import { Component, lazy, Suspense } from 'react'

function OrbFallback() {
  return (
    <div className="absolute inset-0" style={{
      background: 'radial-gradient(ellipse 70% 60% at 50% 50%, #1a1a3e 0%, #06060f 65%)'
    }} />
  )
}

class OrbBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <OrbFallback />
    return this.props.children
  }
}

// Dynamic import so @react-three/fiber is never loaded at module-eval time.
// If WebGL is unavailable (Playwright, headless), the .catch returns OrbFallback
// and the rest of the app renders normally.
const GradientOrbLazy = lazy(() =>
  import('@/components/ui/gradient-orb')
    .then(m => ({ default: m.GradientOrb }))
    .catch(() => ({ default: OrbFallback }))
)

const STATE_CFG = {
  idle: {
    hue: 0,
    rotationSpeed: 0.25,
    noiseScale: 0.65,
    innerRadius: 0.10,
    background: '#06060f',
  },
  thinking: {
    hue: 40,
    rotationSpeed: 0.55,
    noiseScale: 0.85,
    innerRadius: 0.12,
    background: '#06060f',
  },
  streaming: {
    hue: -80,
    rotationSpeed: 0.90,
    noiseScale: 1.10,
    innerRadius: 0.06,
    background: '#06060f',
  },
  disconnected: {
    hue: 200,
    rotationSpeed: 0.04,
    noiseScale: 0.40,
    innerRadius: 0.22,
    background: '#06060f',
  },
}

export default function OrbScene({ orbState }) {
  const cfg = STATE_CFG[orbState] ?? STATE_CFG.idle

  return (
    <div
      className="absolute inset-0 transition-opacity duration-1000"
      style={{ opacity: orbState === 'disconnected' ? 0.45 : 1 }}
    >
      <OrbBoundary>
        <Suspense fallback={<OrbFallback />}>
          <GradientOrbLazy config={cfg} className="absolute inset-0" />
        </Suspense>
      </OrbBoundary>
    </div>
  )
}
