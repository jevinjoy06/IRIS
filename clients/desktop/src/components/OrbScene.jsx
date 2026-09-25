import { GradientOrb } from '@/components/ui/gradient-orb'

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
      <GradientOrb config={cfg} className="absolute inset-0" />
      <div className="absolute bottom-20 left-0 right-0 flex justify-center pointer-events-none z-10">
        <span className="text-[11px] font-mono tracking-[0.2em] uppercase text-white/30 select-none">
          {STATUS_LABEL[orbState] ?? 'Ready'}
        </span>
      </div>
    </div>
  )
}
