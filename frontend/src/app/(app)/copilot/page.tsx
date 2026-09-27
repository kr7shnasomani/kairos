"use client";

import { useEffect, useRef, useState } from "react";
import { SUGGESTIONS, metaAnswer, type CopilotAnswer } from "@/lib/copilot";
import { synthesize } from "@/lib/api";
import { Answer, AnswerError, Thinking, SYNTHESIS_ENABLED } from "./_components/answer-card";
import { Composer } from "./_components/composer";
import { cn } from "@/lib/utils";

import { Icon } from "@/components/icon";
interface Turn {
  id: number;
  query: string;
  asOf?: string;
  answer: CopilotAnswer | null;
  /** Set when retrieval or synthesis failed. The turn shows an error + retry —
   *  never a fabricated answer. */
  error?: string;
  /** Answer text streamed so far. PROVISIONAL — the safety gate can still replace the whole
   *  answer with a refusal, and safety-critical categories never stream at all. Held separately
   *  from `answer` so it is rendered as in-progress text and discarded once `answer` arrives. */
  streaming?: string;
}

function InfoPopover({ turnCount, asOf, onClose }: { turnCount: number; asOf: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50" onClick={onClose}>
      <div
        className="absolute right-4 top-[60px] w-72 rounded-2xl border border-line bg-surface p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p className="text-micro font-bold uppercase tracking-[0.1em] text-accent">Governed answers</p>
          <button
            onClick={onClose}
            aria-label="Close info"
            className="grid size-7 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <Icon name="x" size={14} />
          </button>
        </div>
        <h3 className="mt-1.5 text-title font-semibold">Evidence before prose</h3>
        <p className="mt-2 text-caption leading-relaxed text-muted">
          Kairos cites governed sources, exposes uncertainty, and refuses safety-critical answers when confidence is insufficient.
        </p>
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <div>
            <p className="text-micro font-semibold uppercase tracking-[0.1em] text-muted">Query scope</p>
            <p className="mt-1 text-caption font-medium text-ink">
              {asOf ? `Knowledge valid on ${asOf}` : "Current governed knowledge"}
            </p>
          </div>
          <div>
            <p className="text-micro font-semibold uppercase tracking-[0.1em] text-muted">Conversation</p>
            <p className="mt-1 text-caption tabular text-ink">
              {turnCount} {turnCount === 1 ? "question" : "questions"} in this session
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// sessionStorage, not localStorage: the conversation should survive navigating away and back
// within a tab (the reported bug), but a closed tab or a fresh login is a clean slate rather
// than the last presenter's questions still sitting there.
const STORAGE_KEY = "kairos:copilot:turns";

export default function CopilotPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [input, setInput] = useState("");
  const [asOf, setAsOf] = useState("");
  const [infoOpen, setInfoOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);

  // Restored client-side only, after mount — reading sessionStorage during the initial
  // render would fight SSR hydration, since the server always renders the empty state.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      const restored: Turn[] = raw ? JSON.parse(raw) : [];
      if (restored.length > 0) {
        // A turn saved mid-flight restores stuck, and nothing re-triggers `run()` for it — two
        // shapes, both need catching. Retrieval hadn't even returned yet: `answer` is still
        // null. Retrieval returned but synthesis hadn't: `onSources` already replaced `answer`
        // with a partial CopilotAnswer carrying `is_synthesizing: true` (confirmed live — this
        // is the shape that actually gets saved in practice, since retrieval is fast and wins
        // the race almost every time). Either way it would render <Thinking/> forever without
        // this; convert both into a normal retryable error instead of a permanently stuck spinner.
        const settled = restored.map((t) =>
          (t.answer === null || t.answer.is_synthesizing) && !t.error
            ? { ...t, answer: null, error: "Interrupted — synthesis was still running when you left this page.", streaming: undefined }
            : t
        );
        // eslint-disable-next-line react-hooks/set-state-in-effect -- reading external sessionStorage state on mount is what effects are for
        setTurns(settled);
        nextId.current = Math.max(0, ...settled.map((t) => t.id + 1));
      }
    } catch {
      // Corrupt or unavailable storage — start with an empty conversation rather than throw.
    }
    setHydrated(true);
  }, []);

  // Guarded on `hydrated` so this can't fire on mount, before the restore above has applied,
  // and overwrite a saved conversation with the empty initial state.
  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(turns));
    } catch {
      // Storage full or unavailable — the conversation still works in-memory, it just won't
      // survive navigation this time.
    }
  }, [turns, hydrated]);

  function newChat() {
    setTurns([]);
    nextId.current = 0;
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function run(id: number, q: string, at?: string) {
    setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, answer: null, error: undefined } : turn)));

    // "hello" / "what can you do?" are about the assistant, not the plant. Answering them
    // locally avoids a ~40 s synthesis call that would retrieve nothing relevant and come back
    // with a refusal or an answer stitched from unrelated documents. Plant questions are
    // untouched — metaAnswer returns null for anything it does not explicitly recognise.
    const meta = metaAnswer(q);
    if (meta) {
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, answer: meta } : turn)));
      return;
    }

    synthesize(
      q,
      at,
      (partial) => {
        setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, answer: partial } : turn)));
      },
      // Progressive render. p95 synthesis is ~65 s against NVIDIA's shared endpoint, so without
      // this the operator watches a spinner for over a minute.
      //
      // `streaming_text` is held on the turn, NOT merged into `answer`: the backend can still
      // convert a finished answer into a refusal (and withholds text entirely for safety-critical
      // categories), so this text is provisional until the promise resolves. Rendering it as the
      // answer would show a claim the safety gate is about to retract.
      (accumulated) => {
        setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, streaming: accumulated } : turn)));
      },
    )
      .then((answer) => {
        setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, answer } : turn)));
      })
      .catch((e: unknown) => {
        const message = e instanceof Error ? e.message : "Live data is unavailable.";
        setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, error: message } : turn)));
      });
  }

  function ask(query: string) {
    const q = query.trim();
    if (!q) return;
    const id = nextId.current++;
    const at = asOf || undefined;
    setInput("");
    setTurns((t) => [...t, { id, query: q, asOf: at, answer: null }]);
    run(id, q, at);
  }

  const empty = turns.length === 0;

  return (
    <div data-testid="copilot-workspace" className="relative flex flex-col h-[calc(100dvh-56px)] md:h-[calc(100dvh-64px)] lg:h-dvh w-full">
      {/* New chat — only meaningful once there is a conversation to leave behind */}
      {!empty && (
        <button
          type="button"
          onClick={newChat}
          aria-label="Start a new chat"
          className="fill-sweep absolute right-14 top-4 z-40 inline-flex h-8 items-center gap-1.5 border border-line px-3 text-caption font-medium text-muted"
        >
          <span className="relative z-10 inline-flex items-center gap-1.5">
            <Icon name="plus" size={14} />
            New chat
          </span>
        </button>
      )}

      {/* ⓘ absolute top-right inside the workspace */}
      <button
        id="copilot-info-btn"
        onClick={() => setInfoOpen((v) => !v)}
        aria-label="About governed answers"
        aria-expanded={infoOpen}
        className={cn(
          "absolute right-4 top-4 z-40 grid size-8 place-items-center border text-muted transition-colors",
          infoOpen
            ? "border-accent bg-accent-soft text-accent"
            : "border-transparent hover:border-line hover:text-ink hover:bg-surface-2"
        )}
      >
        <Icon name="info" size={18} />
      </button>

      {infoOpen && (
        <InfoPopover turnCount={turns.length} asOf={asOf} onClose={() => setInfoOpen(false)} />
      )}

      {/* Conversation scrollable area */}
      <div data-testid="copilot-conversation" className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          {empty ? (
            // The landing's hero voice: display headline with an accent second line,
            // then the suggested questions as a numbered cell mesh.
            <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-10 sm:px-6">
              <p className="mb-4 inline-flex self-start bg-accent px-2.5 py-1 text-label font-semibold uppercase tracking-[0.08em] text-on-accent">
                Copilot
              </p>
              <h1 className="display text-display text-balance text-ink sm:text-hero">
                Ask the knowledge base.
                <span className="block text-accent">It cites, or it refuses.</span>
              </h1>
              <p className="mt-4 max-w-xl text-subtitle leading-relaxed text-muted text-pretty">
                Every answer is assembled from governed source documents with citations and confidence scores. On safety-critical parameters, it refuses rather than guess.
              </p>
              {!SYNTHESIS_ENABLED && (
                <div className="mt-4 inline-flex items-center gap-1.5 self-start border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_8%,transparent)] px-3 py-1.5 text-caption text-caution">
                  <span className="size-1.5 shrink-0 bg-caution" aria-hidden="true" />
                  Showing source documents only. Written answers are switched off on this deployment.
                </div>
              )}
              <div className="mesh stagger mt-8 sm:grid-cols-2">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={s}
                    onClick={() => ask(s)}
                    className="lp-cell group flex items-start gap-3 bg-surface p-4 text-left text-body text-ink"
                  >
                    <span className="tabular pt-0.5 text-label text-accent" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                    <span className="flex-1">{s}</span>
                    <span className="text-muted transition-transform duration-150 ease-out group-hover:translate-x-0.5 group-hover:text-accent" aria-hidden="true">›</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-4 py-8 sm:px-6">
              {turns.map((t) => (
                <div key={t.id} className="flex flex-col gap-4">
                  {/* User bubble — right aligned */}
                  <div className="flex justify-end">
                    <div className="max-w-[80%] space-y-1">
                      <div className="rounded-2xl rounded-br-sm bg-accent px-4 py-3 text-sm leading-relaxed text-on-accent">
                        {t.query}
                      </div>
                      {t.asOf && (
                        <p className="text-right text-label text-muted">
                          as of {new Date(t.asOf).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Kairos avatar + answer */}
                  <div className="flex items-start gap-3">
                    <div className="mt-1 grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft">
                      <Icon name="chat-centered-text" className="size-4 text-accent" />
                    </div>
                    <div className="min-w-0 flex-1">
                      {t.error ? (
                        <AnswerError message={t.error} onRetry={() => run(t.id, t.query, t.asOf)} />
                      ) : t.answer ? (
                        <Answer data={t.answer} query={t.query} streaming={t.streaming} />
                      ) : (
                        <Thinking />
                      )}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>

        {/* Composer — pinned to bottom */}
        <div className="shrink-0 border-t border-line bg-canvas px-4 pb-4 pt-3 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <Composer
              value={input}
              onChange={setInput}
              onSubmit={() => ask(input)}
              asOf={asOf}
              onAsOfChange={setAsOf}
            />
            <p className="mt-2 text-center text-label text-muted">
              Answers cite sources and refuse on safety-critical parameters.
            </p>
          </div>
        </div>
      </div>
  );
}
