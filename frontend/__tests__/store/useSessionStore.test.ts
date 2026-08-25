import { beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "@testing-library/react";
import { useSessionStore } from "@/store/useSessionStore";
import * as endpoints from "@/lib/api/endpoints";

vi.mock("@/lib/api/endpoints");

const guest = {
  id: "guest-1",
  kind: "guest" as const,
  email: null,
  name: null,
  avatar: null,
  hasActivity: false,
};

beforeEach(() => {
  useSessionStore.setState({ session: null, providers: [], sessionVersion: 0 });
  vi.resetAllMocks();
});

describe("loading", () => {
  it("holds the session and the providers", async () => {
    vi.mocked(endpoints.fetchSession).mockResolvedValue(guest);
    vi.mocked(endpoints.fetchProviders).mockResolvedValue([{ name: "google", label: "Google" }]);

    await act(async () => {
      await useSessionStore.getState().load();
    });

    expect(useSessionStore.getState().session).toEqual(guest);
    expect(useSessionStore.getState().providers).toHaveLength(1);
  });

  it("survives a provider list that fails", async () => {
    // A deployment with no providers is the normal case, not an error state;
    // the session must still load so the app renders.
    vi.mocked(endpoints.fetchSession).mockResolvedValue(guest);
    vi.mocked(endpoints.fetchProviders).mockRejectedValue(new Error("nope"));

    await act(async () => {
      await useSessionStore.getState().load();
    });

    expect(useSessionStore.getState().session).toEqual(guest);
    expect(useSessionStore.getState().providers).toEqual([]);
  });
});

describe("sessionVersion", () => {
  it("bumps on sign out", async () => {
    vi.mocked(endpoints.logout).mockResolvedValue(undefined);
    vi.mocked(endpoints.fetchSession).mockResolvedValue(guest);
    vi.mocked(endpoints.fetchProviders).mockResolvedValue([]);

    const before = useSessionStore.getState().sessionVersion;
    await act(async () => {
      await useSessionStore.getState().signOut();
    });

    expect(useSessionStore.getState().sessionVersion).toBe(before + 1);
  });

  it("bumps on a completed claim", async () => {
    vi.mocked(endpoints.confirmClaim).mockResolvedValue(undefined);
    vi.mocked(endpoints.fetchSession).mockResolvedValue({ ...guest, kind: "user" });
    vi.mocked(endpoints.fetchProviders).mockResolvedValue([]);

    const before = useSessionStore.getState().sessionVersion;
    await act(async () => {
      await useSessionStore.getState().claim("tok");
    });

    expect(useSessionStore.getState().sessionVersion).toBe(before + 1);
  });

  it("does not bump when the claim is refused", async () => {
    // The cookie did not move, so nothing downstream is stale -- a bump would
    // refetch every panel to redraw the same numbers.
    vi.mocked(endpoints.confirmClaim).mockRejectedValue(new Error("invalid"));

    const before = useSessionStore.getState().sessionVersion;
    await act(async () => {
      await expect(useSessionStore.getState().claim("tok")).rejects.toThrow();
    });

    expect(useSessionStore.getState().sessionVersion).toBe(before);
  });
});
