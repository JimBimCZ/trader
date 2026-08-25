import Link from "next/link";

/**
 * The bottom edge of the workspace: what the numbers above are worth, and
 * where the privacy policy is. Nothing else earns a permanent line here.
 *
 * The muted tone rather than the faint one this size invites -- `textFaint`
 * is 2.9:1 on the light canvas, under the floor §10 sets for small text, and
 * 11px is where that floor matters most.
 */
export function Footer() {
  return (
    <footer className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t-hairline border-border px-1 pt-2 text-[11px] text-text-muted">
      <p>Simulated trading with virtual money — not financial advice.</p>
      <Link href="/privacy/" className="text-blue-text hover:underline">
        Privacy
      </Link>
    </footer>
  );
}
