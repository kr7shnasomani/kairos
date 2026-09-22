"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

import { Icon } from "@/components/icon";
type Theme = "light" | "dark";

/** Flips the single Kairos UI between its light and dark palettes. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    // Mount-once sync of the pre-hydration <html data-theme> into React state.
    const current = document.documentElement.getAttribute("data-theme");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reading external DOM state on mount is what effects are for
    if (current === "dark" || current === "light") setTheme(current);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    const apply = () => {
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("kairos-theme", next); } catch { /* no-op */ }
    };
    // Crossfade the palette flip where the browser supports it. A hard swap of
    // every surface at once reads as a glitch; the snapshot fade reads as a change
    // of light. Unsupported browsers and reduced-motion users get the instant swap.
    const startViewTransition = document.startViewTransition?.bind(document);
    if (!startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      apply();
      return;
    }
    startViewTransition(apply);
  }

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={isDark}
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      title={`Switch to ${isDark ? "light" : "dark"} mode`}
      className={cn("grid size-8 place-items-center text-muted transition-colors hover:bg-surface-2 hover:text-ink", className)}
    >
      {isDark ? (
        <Icon name="sun" size={15} />
      ) : (
        <Icon name="moon" size={15} />
      )}
    </button>
  );
}

/** Sunlight / high-contrast toggle — third palette for outdoor legibility. */
export function ContrastToggle({ className = "" }: { className?: string }) {
  const [high, setHigh] = useState(false);

  useEffect(() => {
    // Mount-once sync of the pre-hydration <html data-contrast> into React state.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reading external DOM state on mount is what effects are for
    setHigh(document.documentElement.getAttribute("data-contrast") === "high");
  }, []);

  function toggle() {
    const next = !high;
    setHigh(next);
    if (next) {
      document.documentElement.setAttribute("data-contrast", "high");
    } else {
      document.documentElement.removeAttribute("data-contrast");
    }
    try { localStorage.setItem("kairos-contrast", next ? "high" : ""); } catch { /* no-op */ }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={high}
      aria-label={high ? "Disable sunlight mode" : "Enable sunlight mode"}
      title={high ? "Disable sunlight mode" : "Sunlight / high-contrast mode"}
      className={cn("grid size-8 place-items-center text-muted transition-colors hover:bg-surface-2", high ? "text-caution" : "hover:text-ink", className)}
    >
      <Icon name="sun" size={15} />
    </button>
  );
}
