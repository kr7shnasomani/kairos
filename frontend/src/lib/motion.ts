"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const mq = window.matchMedia(REDUCE_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

/** Live prefers-reduced-motion flag. SSR-safe (false on the server). */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCE_QUERY).matches,
    () => false,
  );
}

/** rAF count-up toward `target` from the previously shown value.
 *  Snaps instantly under prefers-reduced-motion and on the server. */
export function useCountUp(target: number, duration = 600): number {
  const [value, setValue] = useState(target);
  const prev = useRef(target);
  const mounted = useRef(false);

  useEffect(() => {
    // First client render shows the real value; animate only on changes after mount.
    if (!mounted.current) {
      mounted.current = true;
      prev.current = target;
      return;
    }
    const reducedMotion =
      typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Browsers pause requestAnimationFrame in a hidden tab. Animating there left every
    // KpiCard showing its initial value (0) — and because this effect only re-runs when
    // `target` changes, it never corrected once the tab became visible. When the value
    // cannot be animated, commit it on a timer instead: timers are throttled in a hidden
    // tab but they do fire, whereas rAF does not. Deferred rather than set synchronously so
    // this does not cascade a render inside the effect.
    if (reducedMotion || (typeof document !== "undefined" && document.hidden)) {
      prev.current = target;
      const timer = setTimeout(() => setValue(target), 0);
      return () => clearTimeout(timer);
    }
    const from = prev.current;
    prev.current = target;
    if (from === target) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - (1 - p) ** 3; // ease-out cubic
      setValue(from + (target - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return value;
}

/** Reveal-once-on-scroll. Consumer applies the transition classes and flips
 *  them on `revealed`. Reduced motion (or no IntersectionObserver) reveals
 *  immediately — content is never hidden from anyone. */
export function useScrollReveal<T extends HTMLElement>(threshold = 0.15): {
  ref: React.RefObject<T | null>;
  revealed: boolean;
} {
  const ref = useRef<T | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    const reduce = typeof window.matchMedia === "function" && window.matchMedia(REDUCE_QUERY).matches;
    if (!el || reduce || typeof IntersectionObserver === "undefined") {
      const raf = requestAnimationFrame(() => setRevealed(true));
      return () => cancelAnimationFrame(raf);
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setRevealed(true);
          io.disconnect();
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);

  return { ref, revealed };
}

/** Inline style for staggered list entrances (pair with animate-[rise-in_…]).
 *  Delay is capped so long lists don't crawl in. */
export function staggerDelay(index: number, step = 35, max = 350): React.CSSProperties {
  return { animationDelay: `${Math.min(index * step, max)}ms`, animationFillMode: "backwards" };
}
