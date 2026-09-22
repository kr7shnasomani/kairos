"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

import { Icon } from "@/components/icon";
// Web Speech API — not available in all browsers; typed as any to avoid lib conflicts.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SpeechRecogAny = any;

export function Composer({
  value,
  onChange,
  onSubmit,
  asOf,
  onAsOfChange,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  asOf: string;
  onAsOfChange: (v: string) => void;
}) {
  const [listening, setListening] = useState(false);
  const [showAsOf, setShowAsOf] = useState(false);
  const recogRef = useRef<SpeechRecogAny>(null);
  const hasSpeech =
    typeof window !== "undefined" &&
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const today =
    typeof window !== "undefined" ? new Date().toISOString().split("T")[0] : undefined;

  function toggleVoice() {
    if (listening) {
      recogRef.current?.stop();
      setListening(false);
      return;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const win = window as any;
    const SR = win.SpeechRecognition ?? win.webkitSpeechRecognition;
    const r = new SR();
    r.lang = "en-IN";
    r.interimResults = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    r.onresult = (e: any) => {
      const transcript = e.results[0]?.[0]?.transcript ?? "";
      if (transcript) onChange((value ? value + " " : "") + transcript);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    r.start();
    recogRef.current = r;
    setListening(true);
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Time-travel date picker — shown when toggled or when a date is set */}
      {(showAsOf || asOf) && (
        <div className="flex items-center gap-2 text-label">
          <label htmlFor="copilot-asof" className="font-medium text-muted">
            As of
          </label>
          <input
            id="copilot-asof"
            type="date"
            value={asOf}
            onChange={(e) => onAsOfChange(e.target.value)}
            max={today}
          className="min-h-11 rounded-md border border-line bg-surface px-2 py-1 text-label outline-none focus-visible:border-accent"
          />
          {asOf && (
            <button
              type="button"
              onClick={() => {
                onAsOfChange("");
                setShowAsOf(false);
              }}
              className="min-h-11 px-2 text-muted transition-colors hover:text-ink"
              aria-label="Clear time travel date"
            >
              Clear
            </button>
          )}
        </div>
      )}

      <form
        data-testid="copilot-composer"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="flex min-h-11 items-center gap-2 rounded-2xl border border-line bg-surface py-2 pl-4 pr-2 focus-within:border-[color-mix(in_srgb,var(--accent)_45%,var(--line))]"
      >
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Ask about an asset, failure, procedure, or requirement…"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
          aria-label="Ask the copilot"
        />

        {/* Time-travel toggle */}
        <button
          type="button"
          onClick={() => setShowAsOf((v) => !v)}
          aria-label={asOf ? `Time travel set: ${asOf}` : "Set time travel date"}
          aria-pressed={showAsOf || !!asOf}
          title="Query as of a past date"
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-xl transition-colors",
            asOf
              ? "bg-accent-soft text-accent"
              : "text-muted hover:bg-surface-2 hover:text-ink"
          )}
        >
          <Icon name="clock-counter-clockwise" size={16} />
        </button>

        {hasSpeech && (
          <button
            type="button"
            onClick={toggleVoice}
            aria-label={listening ? "Stop listening" : "Speak your question"}
            aria-pressed={listening}
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-xl transition-colors",
              listening
                ? "bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-danger"
                : "text-muted hover:bg-surface-2 hover:text-ink"
            )}
          >
            <Icon name="microphone" size={17} />
          </button>
        )}

        <button
          type="submit"
          disabled={!value.trim()}
          aria-label="Send"
          className="grid size-11 shrink-0 place-items-center rounded-xl bg-accent text-on-accent transition-opacity disabled:opacity-40"
        >
          <Icon name="paper-plane-right" size={17} />
        </button>
      </form>
    </div>
  );
}
