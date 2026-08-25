import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClaimConflictDialog } from "@/components/layout/ClaimConflictDialog";
import { useSessionStore } from "@/store/useSessionStore";

function visit(search: string) {
  window.history.replaceState({}, "", `/${search}`);
}

beforeEach(() => {
  useSessionStore.setState({ claim: vi.fn().mockResolvedValue(undefined) });
});

it("stays closed without the query parameters", () => {
  visit("");
  render(<ClaimConflictDialog />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("opens on a conflict redirect", () => {
  visit("?claim=conflict&token=tok");
  render(<ClaimConflictDialog />);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("names what will be discarded", () => {
  visit("?claim=conflict&token=tok");
  render(<ClaimConflictDialog />);
  expect(screen.getByText(/guest activity will be discarded/i)).toBeInTheDocument();
});

it("claims with the token from the URL", async () => {
  const claim = vi.fn().mockResolvedValue(undefined);
  useSessionStore.setState({ claim });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));

  expect(claim).toHaveBeenCalledWith("tok");
});

it("clears the query string so a reload does not re-prompt", async () => {
  visit("?claim=conflict&token=tok");
  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

  await waitFor(() => expect(window.location.search).toBe(""));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps the guest session when cancelled", async () => {
  const claim = vi.fn();
  useSessionStore.setState({ claim });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

  expect(claim).not.toHaveBeenCalled();
});

it("shows the error and stays open when the claim is refused", async () => {
  useSessionStore.setState({
    claim: vi.fn().mockRejectedValue(new Error("That confirmation is no longer valid.")),
  });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));

  expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("dismisses rather than erroring when the claim succeeded but the reload after it failed", async () => {
  // useSessionStore.claim() resolves in this case -- a failing post-claim
  // reload is swallowed there and retried by the page's sessionVersion
  // effect, not surfaced as a refused claim. The dialog has no way to tell
  // this apart from a clean success, which is the point: it should not.
  useSessionStore.setState({ claim: vi.fn().mockResolvedValue(undefined) });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(window.location.search).toBe("");
});
