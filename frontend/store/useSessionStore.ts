"use client";

import { create } from "zustand";
import { confirmClaim, fetchProviders, fetchSession, logout } from "@/lib/api/endpoints";
import type { AuthProvider, Session } from "@/lib/types";

interface SessionState {
  session: Session | null;
  providers: AuthProvider[];
  /**
   * Bumped whenever the cookie starts pointing at a different person. Every
   * other store keys its refetch off this: after a sign-out or a claim the
   * same URL is a different portfolio, and the stores holding the previous
   * identity's positions have no other way to learn that.
   */
  sessionVersion: number;
  load: () => Promise<void>;
  signOut: () => Promise<void>;
  claim: (token: string) => Promise<void>;
}

export const useSessionStore = create<SessionState>()((set, get) => ({
  session: null,
  providers: [],
  sessionVersion: 0,

  load: async () => {
    const session = await fetchSession();
    // A deployment with no OAuth credentials is the normal case rather than a
    // failure, so a providers call that goes wrong must not stop the session
    // from loading -- the app renders guest-only, which is correct anyway.
    let providers: AuthProvider[] = [];
    try {
      providers = await fetchProviders();
    } catch {
      providers = [];
    }
    set({ session, providers });
  },

  signOut: async () => {
    await logout();
    await get().load();
    set((state) => ({ sessionVersion: state.sessionVersion + 1 }));
  },

  claim: async (token: string) => {
    // No try/catch around confirmClaim: a refused claim leaves the cookie
    // exactly where it was, so nothing downstream is stale and the caller
    // renders the error.
    await confirmClaim(token);

    // confirmClaim resolving IS the moment the cookie moved to the target
    // account -- that fact does not depend on the reload below succeeding.
    // Bumping here (rather than after `load()`) means a reload that fails on
    // a network blip still leaves every other store correctly informed that
    // the identity changed, instead of stranding the caller with a token
    // that a moved cookie has already made unusable to retry.
    set((state) => ({ sessionVersion: state.sessionVersion + 1 }));
    // The claim itself has succeeded by here, so a failing reload must not be
    // reported to the caller as a refused claim -- that would leave the dialog
    // open offering a retry that cannot work, since the token is bound to a
    // session the cookie has already left. The version bump above drives the
    // page's refetch, which reloads the session too.
    try {
      await get().load();
    } catch {
      // Deliberately swallowed; the refetch keyed on sessionVersion retries it.
    }
  },
}));
