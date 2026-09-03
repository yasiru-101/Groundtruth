import { useEffect, useState } from "react"

import { scoreBgClass, scoreColorClass } from "@/score-band"

interface ScoreGaugeProps {
  value: number
  size?: number
  stroke?: number
}

export function ScoreGauge({ value, size = 160, stroke = 12 }: ScoreGaugeProps) {
  const [display, setDisplay] = useState(0)
  const radius = (size - stroke) / 2
  const circumference = radius * 2 * Math.PI
  const progress = Math.min(Math.max(display, 0), 1)
  const offset = circumference - progress * circumference

  useEffect(() => {
    const duration = 1200
    const start = performance.now()
    const startValue = display
    const animate = (now: number) => {
      const t = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3)
      setDisplay(startValue + (value - startValue) * eased)
      if (t < 1) requestAnimationFrame(animate)
    }
    const raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [value])

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-muted/20"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          className={scoreBgClass(value)}
          style={{
            strokeDasharray: circumference,
            strokeDashoffset: offset,
            transition: "stroke-dashoffset 1.2s ease-out",
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-4xl font-bold tabular-nums ${scoreColorClass(value)}`}>
          {Math.round(display * 100)}
        </span>
        <span className="text-xs text-muted-foreground">truthfulness</span>
      </div>
    </div>
  )
}
