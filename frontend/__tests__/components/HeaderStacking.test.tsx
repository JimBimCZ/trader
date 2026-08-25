import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "@/components/layout/Header";
import { useSessionStore } from "@/store/useSessionStore";

/**
 * jsdom has no layout, so it cannot tell us what paints over what. What it can
 * hold is the property the painting depends on.
 *
 * `.material` carries `backdrop-filter`, which makes the toolbar its own
 * stacking context. Anything absolutely positioned inside it — the sign-in
 * sheet, the account menu — is sealed into that context, so their `z-20`
 * competes only with each other and never with `<main>`. The toolbar is
 * earlier in the DOM than `<main>`, so at `z-index: auto` the chat panel
 * simply paints over the open sheet.
 *
 * The toolbar therefore has to be a positioned layer of its own, above the
 * workspace and below the modal at `z-50`.
 */
beforeEach(() => {
  useSessionStore.setState({
    session: { id: "u1", kind: "guest", email: null, name: null, avatar: null, hasActivity: false },
    providers: [{ name: "google", label: "Google" }],
    sessionVersion: 0,
  });
});

describe("the toolbar as a stacking layer", () => {
  it("is positioned, so its z-index applies at all", () => {
    render(<Header />);
    expect(screen.getByRole("banner").className).toMatch(/\brelative\b/);
  });

  it("sits above the workspace and below the modal layer", () => {
    render(<Header />);
    const z = screen.getByRole("banner").className.match(/\bz-(\d+)\b/);
    expect(z, "the toolbar needs an explicit z-index").not.toBeNull();
    const level = Number(z![1]);
    expect(level).toBeGreaterThan(20); // above the sheet's own layer and the workspace
    expect(level).toBeLessThan(50); // below ClaimConflictDialog's backdrop
  });
});
