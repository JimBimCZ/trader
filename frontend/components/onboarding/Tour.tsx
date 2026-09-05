"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { TOUR_STEPS, type TourStep } from "./steps";

export const TOUR_STORAGE_KEY = "trader-tour-seen";

function seen(): boolean {
  try {
    return window.localStorage.getItem(TOUR_STORAGE_KEY) !== null;
  } catch {
    // Private browsing denies storage. A first-run affordance is not state
    // worth defending, so an unreadable key means "show it".
    return false;
  }
}

/** Only the steps whose target is actually on this screen. */
function reachable(): TourStep[] {
  return TOUR_STEPS.filter((step) => document.getElementById(step.target) !== null);
}

/**
 * A guided walk around the real UI, for a visitor who has not signed in.
 *
 * The spotlight is one rect over the step's target with a 9999px box-shadow
 * standing in for a cut-out -- no clip-path, no second overlay, no library.
 */
export function Tour() {
  const session = useSessionStore((s) => s.session);
  const [steps, setSteps] = useState<TourStep[] | null>(null);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const isGuest = session?.kind === "guest";

  // Resolved once, after mount: the targets have to exist to be measured, and
  // a step pointing at nothing would spotlight a zero rect.
  useEffect(() => {
    if (!isGuest || seen()) return;
    setSteps(reachable());
  }, [isGuest]);

  const step = steps?.[index];

  useEffect(() => {
    if (!step) return;
    const measure = () => {
      const target = document.getElementById(step.target);
      setRect(target ? target.getBoundingClientRect() : null);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [step]);

  const dismiss = useCallback(() => {
    setSteps(null);
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, "1");
    } catch {
      // The tour will show again next visit. Acceptable; storing it is a
      // convenience, not a contract.
    }
  }, []);

  useEffect(() => {
    if (!step) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, dismiss]);

  useEffect(() => {
    cardRef.current?.focus();
  }, [index]);

  if (!steps || steps.length === 0 || !step) return null;

  const last = index === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[90]">
      {rect && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-card transition-[top,left,width,height] duration-200 motion-reduce:transition-none"
          style={{
            top: rect.top - 4,
            left: rect.left - 4,
            width: rect.width + 8,
            height: rect.height + 8,
            boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.45)",
          }}
        />
      )}

      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        tabIndex={-1}
        className="material absolute left-1/2 bottom-8 w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 rounded-card p-4 shadow-pop outline-none"
      >
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
          {index + 1} of {steps.length}
        </p>
        <h2 id="tour-title" className="mt-1 text-[15px] font-semibold tracking-[-0.01em] text-text">
          {step.title}
        </h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-muted">{step.body}</p>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={dismiss}
            className="rounded-control px-3 py-1.5 text-[13px] font-medium text-text-muted transition hover:bg-surface-sunk"
          >
            Skip
          </button>
          <button
            onClick={() => (last ? dismiss() : setIndex((i) => i + 1))}
            className="rounded-control bg-blue-fill px-3 py-1.5 text-[13px] font-semibold text-white transition hover:opacity-90"
          >
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
