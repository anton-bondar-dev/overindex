import { useEffect, useRef, useState } from 'react'

const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t))

/** rAF scroll to an absolute document Y with an eased curve. Native
 *  scroll-behavior:smooth is distance-dependent and overshoots — this is
 *  constant-duration and clean on a long page (used only by the demo driver). */
export function smoothScrollTo(top: number, durationMs: number): Promise<void> {
  return new Promise((resolve) => {
    const start = window.scrollY
    const dist = top - start
    if (Math.abs(dist) < 2 || durationMs <= 0) {
      window.scrollTo(0, top)
      resolve()
      return
    }
    const t0 = performance.now()
    const frame = (now: number) => {
      const p = Math.min(1, (now - t0) / durationMs)
      window.scrollTo(0, start + dist * easeInOutCubic(p))
      if (p < 1) requestAnimationFrame(frame)
      else resolve()
    }
    requestAnimationFrame(frame)
  })
}

/** Counts from 0 to target once `start` flips true; otherwise shows target. */
export function useCountUp(target: number, start: boolean, durationMs = 1000): number {
  const [val, setVal] = useState(start ? 0 : target)
  const ran = useRef(false)
  useEffect(() => {
    if (!start || ran.current) return
    ran.current = true
    const t0 = performance.now()
    let raf = 0
    const frame = (now: number) => {
      const p = Math.min(1, (now - t0) / durationMs)
      setVal(Math.round(target * easeOutExpo(p)))
      if (p < 1) raf = requestAnimationFrame(frame)
      else setVal(target)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [start, target, durationMs])
  return val
}

/** Fires true once the element is sufficiently on-screen (then stops observing). */
export function useInView<T extends Element>(threshold = 0.5): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null)
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setInView(true)
          io.disconnect()
        }
      },
      { threshold },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [threshold])
  return [ref, inView]
}
