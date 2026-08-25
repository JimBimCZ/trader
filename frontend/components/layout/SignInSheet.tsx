"use client";

import type { AuthProvider } from "@/lib/types";

/**
 * The provider list, as a sheet hanging off the toolbar.
 *
 * Each provider is an `<a>`, not a fetch: sign-in is a full-page navigation,
 * which is what makes it work from a static export. A button posting through
 * the API client would land the provider's consent screen inside an XHR.
 *
 * Buttons wear the neutral fill rather than Google's or GitHub's brand
 * colours -- those would be the only non-systemBlue interaction colours in the
 * app, and would read as an advertisement rather than as a control.
 */
export function SignInSheet({ providers }: { providers: AuthProvider[] }) {
  return (
    <div
      role="dialog"
      aria-label="Sign in"
      className="material absolute right-0 top-full z-20 mt-2 w-64 rounded-card p-3 shadow-pop"
    >
      <p className="field-label px-1">Sign in</p>
      <p className="mt-1 px-1 text-[12px] leading-snug text-text-muted">
        Keeps this portfolio when you change browser.
      </p>
      <div className="mt-3 flex flex-col gap-2">
        {providers.map((provider) => (
          <a
            key={provider.name}
            href={`/api/auth/login/${provider.name}`}
            className="flex h-9 items-center justify-center rounded-control bg-surface-sunk text-[13px] font-semibold text-text transition-colors hover:brightness-95 dark:hover:brightness-125"
          >
            Continue with {provider.label}
          </a>
        ))}
      </div>
    </div>
  );
}
