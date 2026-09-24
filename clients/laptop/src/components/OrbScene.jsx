import { Canvas, useFrame } from '@react-three/fiber'
import { MeshDistortMaterial, Sphere, Float, Torus } from '@react-three/drei'
import { useRef } from 'react'
import * as THREE from 'three'

const STATE_CFG = {
  idle:         { distort: 0.25, speed: 1.2, color: '#1d4ed8', emissive: '#1e40af', emissiveIntensity: 0.35, light: 1.8 },
  thinking:     { distort: 0.55, speed: 4.0, color: '#6d28d9', emissive: '#7c3aed', emissiveIntensity: 0.8,  light: 3.5 },
  streaming:    { distort: 0.72, speed: 6.0, color: '#1d4ed8', emissive: '#3b82f6', emissiveIntensity: 1.1,  light: 5.0 },
  disconnected: { distort: 0.10, speed: 0.4, color: '#3b0a0a', emissive: '#7f1d1d', emissiveIntensity: 0.2,  light: 0.4 },
}

function IrisOrb({ orbState }) {
  const matRef   = useRef()
  const lightRef = useRef()
  const ring1Ref = useRef()
  const ring2Ref = useRef()

  useFrame((_, delta) => {
    const cfg = STATE_CFG[orbState] ?? STATE_CFG.idle
    const k   = Math.min(delta * 2.5, 1)

    if (matRef.current) {
      matRef.current.distort           = THREE.MathUtils.lerp(matRef.current.distort, cfg.distort, k)
      matRef.current.speed             = THREE.MathUtils.lerp(matRef.current.speed, cfg.speed, k)
      matRef.current.emissiveIntensity = THREE.MathUtils.lerp(matRef.current.emissiveIntensity, cfg.emissiveIntensity, k)
    }
    if (lightRef.current) {
      lightRef.current.intensity = THREE.MathUtils.lerp(lightRef.current.intensity, cfg.light, k)
    }
    if (ring1Ref.current) ring1Ref.current.rotation.z += delta * 0.35
    if (ring2Ref.current) ring2Ref.current.rotation.x += delta * 0.22
  })

  const cfg = STATE_CFG[orbState] ?? STATE_CFG.idle

  return (
    <>
      <ambientLight intensity={0.08} />
      <pointLight ref={lightRef} position={[0, 0, 3]} intensity={cfg.light} color="#7bb3ff" />
      <pointLight position={[-3, 2, -2]} intensity={0.6} color="#a78bfa" />

      {/* Outer orbiting rings */}
      <Torus ref={ring1Ref} args={[1.65, 0.012, 8, 120]}>
        <meshBasicMaterial color="#3b82f6" transparent opacity={0.3} />
      </Torus>
      <Torus ref={ring2Ref} args={[1.95, 0.008, 8, 120]} rotation={[Math.PI / 3, 0, 0]}>
        <meshBasicMaterial color="#8b5cf6" transparent opacity={0.18} />
      </Torus>

      {/* Core orb with gentle float */}
      <Float speed={1.4} rotationIntensity={0.35} floatIntensity={0.55}>
        <Sphere args={[1, 64, 64]}>
          <MeshDistortMaterial
            ref={matRef}
            color={cfg.color}
            emissive={cfg.emissive}
            emissiveIntensity={cfg.emissiveIntensity}
            distort={cfg.distort}
            speed={cfg.speed}
            roughness={0.08}
            metalness={0.15}
            transparent
            opacity={0.93}
          />
        </Sphere>
      </Float>
    </>
  )
}

const STATUS_LABEL = {
  idle:         'Ready',
  thinking:     'Thinking...',
  streaming:    'Speaking...',
  disconnected: 'Offline',
}

export default function OrbScene({ orbState }) {
  return (
    <div className="relative w-full h-full">
      <Canvas camera={{ position: [0, 0, 3.8], fov: 42 }} style={{ background: 'transparent' }}>
        <IrisOrb orbState={orbState} />
      </Canvas>

      {/* Status label floating below orb */}
      <div className="absolute bottom-6 left-0 right-0 flex justify-center pointer-events-none">
        <span className="text-[11px] font-mono tracking-[0.2em] uppercase text-white/30 select-none">
          {STATUS_LABEL[orbState] ?? 'Ready'}
        </span>
      </div>
    </div>
  )
}
