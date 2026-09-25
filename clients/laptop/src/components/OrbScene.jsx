import { GradientOrb } from '@/components/ui/gradient-orb'

// Map each orbState to GradientOrb shader config.
// hue rotates all three base colors (blue/purple/orange) through YIQ color space.
// Higher rotationSpeed and noiseScale = more energetic/turbulent appearance.
const STATE_CFG = {
  idle: {
    hue: 0,           // blue → purple → orange (default palette)
    rotationSpeed: 0.25,
    noiseScale: 0.65,
    innerRadius: 0.10,
    background: '#06060f',
  },
  thinking: {
    hue: 40,          // shifted warmer — more violet/pink
    rotationSpeed: 0.55,
    noiseScale: 0.85,
    innerRadius: 0.12,
    background: '#06060f',
  },
  streaming: {
    hue: -80,         // shifted cooler — cyan/teal tones
    rotationSpeed: 0.90,
    noiseScale: 1.10,
    innerRadius: 0.06,
    background: '#06060f',
  },
  disconnected: {
    hue: 200,         // desaturated bluish
    rotationSpeed: 0.04,
    noiseScale: 0.40,
    innerRadius: 0.22,
    background: '#06060f',
  },
}

const STATUS_LABEL = {
  idle: 'Ready',
  thinking: 'Thinking...',
  streaming: 'Speaking...',
  disconnected: 'Offline',
}

export default function OrbScene({ orbState }) {
  const cfg = STATE_CFG[orbState] ?? STATE_CFG.idle

  return (
    <div className="absolute inset-0">
      {/* Full-screen gradient shader orb — no external assets, CSP-safe */}
      <GradientOrb config={cfg} className="absolute inset-0" />

      {/* Status label floated above the orb */}
      <div className="absolute bottom-20 left-0 right-0 flex justify-center pointer-events-none z-10">
        <span className="text-[11px] font-mono tracking-[0.2em] uppercase text-white/30 select-none">
          {STATUS_LABEL[orbState] ?? 'Ready'}
        </span>
      </div>
    </div>
  )
}
