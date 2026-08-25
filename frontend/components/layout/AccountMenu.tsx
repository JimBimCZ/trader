"use client";

import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { SignInSheet } from "./SignInSheet";

export function AccountMenu() {
  const session = useSessionStore((s) => s.session);
  const providers = useSessionStore((s) => s.providers);
  const signOut = useSessionStore((s) => s.signOut);
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  // Escape and outside-click close it, because a sheet that can only be
  // dismissed by the control that opened it traps keyboard users.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    const onClick = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  if (!session) return null;

  const signedIn = session.kind === "user";
  const label = signedIn ? (session.name ?? session.email ?? "Account") : "Sign in";

  // Nothing to offer and nothing to show: the zero-config deployment renders
  // no control at all rather than a button that dead-ends.
  if (!signedIn && providers.length === 0) return null;

  return (
    <div className="relative flex items-center gap-3" ref={container}>
      {/* Only once there is something to lose. On a fresh visit the portfolio
          is the seeded $10,000 and the line is pure noise. */}
      {!signedIn && session.hasActivity && (
        <p className="hidden text-[12px] text-text-muted lg:block">
          Browsing as a guest — sign in to keep this portfolio
        </p>
      )}

      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-haspopup={signedIn ? "menu" : "dialog"}
        aria-expanded={open}
        className="flex h-8 items-center gap-2 rounded-control px-2.5 text-[13px] font-semibold text-text hover:bg-surface-sunk"
      >
        {signedIn && session.avatar ? (
          // A remote provider avatar; next/image needs a loader the static
          // export has no server to run.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={session.avatar} alt="" className="h-6 w-6 rounded-full" />
        ) : (
          <span
            aria-hidden
            className="grid h-6 w-6 place-items-center rounded-full bg-surface-sunk text-[11px] font-bold"
          >
            {(label[0] ?? "?").toUpperCase()}
          </span>
        )}
        <span className="max-w-[10rem] truncate">{label}</span>
      </button>

      {open && !signedIn && <SignInSheet providers={providers} />}

      {open && signedIn && (
        <div
          role="menu"
          className="material absolute right-0 top-full z-20 mt-2 w-56 rounded-card p-1.5 shadow-pop"
        >
          <p className="truncate px-2.5 py-1.5 text-[12px] text-text-muted">{session.email}</p>
          <div className="mx-2.5 border-t border-hairline border-border" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void signOut();
            }}
            className="mt-1 w-full rounded-control px-2.5 py-1.5 text-left text-[13px] font-medium text-text hover:bg-surface-sunk"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
