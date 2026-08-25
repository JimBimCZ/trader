"use client";

import { useEffect, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { Button } from "@/components/ui/Button";

/**
 * The one sign-in outcome the server refuses to decide alone: a guest with
 * real activity signing into an account that already has a portfolio.
 *
 * It fires only when a collision actually occurred, rather than warning
 * before every sign-in -- a prompt that appears every time trains people to
 * dismiss it, and the one time it matters they will.
 */
export function ClaimConflictDialog() {
  const claim = useSessionStore((s) => s.claim);
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Read only after mount: the page is prerendered as a static export, and
  // touching `window` during render fails that build.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("claim") === "conflict") setToken(params.get("token"));
  }, []);

  // The token is single-use and short-lived, so leaving it in the URL means
  // a reload re-prompts with something that no longer works.
  const dismiss = () => {
    window.history.replaceState({}, "", window.location.pathname);
    setToken(null);
  };

  if (!token) return null;

  const confirm = async () => {
    setPending(true);
    setError(null);
    try {
      await claim(token);
      dismiss();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That confirmation failed.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="claim-title"
        className="w-full max-w-md rounded-card bg-surface p-5 shadow-xl"
      >
        <h2 id="claim-title" className="text-[17px] font-semibold text-text">
          That account already has a portfolio
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-text-muted">
          Signing in opens the portfolio that already belongs to this account. Your current
          guest activity will be discarded and cannot be recovered.
        </p>
        {error && (
          <p role="alert" className="mt-3 text-[12px] font-medium text-down-text">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="plain" onClick={dismiss}>
            Cancel
          </Button>
          <Button type="button" variant="prominent" onClick={confirm} disabled={pending}>
            {pending ? "Signing in…" : "Continue"}
          </Button>
        </div>
      </div>
    </div>
  );
}
