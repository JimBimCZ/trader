import { beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { act } from "react";
import { ThemeSync } from "@/components/layout/ThemeSync";
import { useTheme } from "@/lib/useTheme";
import { palettes } from "@/lib/theme";

/** jsdom has no matchMedia, and the OS preference is the thing under test. */
function stubMatchMedia(matches: boolean) {
  const listeners = new Set<() => void>();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches,
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
    })),
  );
  return {
    listeners,
    flipTo(next: boolean) {
      matches = next;
      vi.stubGlobal(
        "matchMedia",
        vi.fn(() => ({
          matches: next,
          addEventListener: () => {},
          removeEventListener: () => {},
        })),
      );
      act(() => listeners.forEach((fn) => fn()));
    },
  };
}

describe("ThemeSync", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useTheme.setState({ mode: "system", appearance: "light", palette: palettes.light });
    document.documentElement.dataset.theme = "light";
  });

  it("adopts the OS appearance on mount", () => {
    stubMatchMedia(true);
    render(<ThemeSync />);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("keeps following the OS while the page stays open", () => {
    // The pre-paint script resolves the appearance once. Without this, a page
    // that never mounts the store stops tracking the moment it has loaded.
    const media = stubMatchMedia(false);
    render(<ThemeSync />);
    expect(document.documentElement.dataset.theme).toBe("light");

    media.flipTo(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("leaves an explicit choice alone when the OS changes", () => {
    const media = stubMatchMedia(false);
    window.localStorage.setItem("trader-theme", "light");
    render(<ThemeSync />);

    media.flipTo(true);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("drops its listener on unmount", () => {
    const media = stubMatchMedia(true);
    const { unmount } = render(<ThemeSync />);
    expect(media.listeners.size).toBe(1);
    unmount();
    expect(media.listeners.size).toBe(0);
  });
});
