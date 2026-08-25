import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { ThemeSync } from "@/components/layout/ThemeSync";

export const metadata: Metadata = {
  title: "Privacy — Trader",
  description: "What Trader stores, why, and for how long.",
};

/** Kept beside the prose so the two cannot drift apart silently. */
const LAST_UPDATED = "25 August 2026";
const CONTACT = "busek.vit@gmail.com";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t-hairline border-border pt-6">
      <h2 className="mb-2 text-[15px] font-semibold tracking-[-0.01em]">{title}</h2>
      <div className="space-y-3 text-[13px] leading-relaxed text-text-muted">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    // A reading page, so it scrolls and holds a measure -- deliberately not
    // the workspace's fixed viewport split.
    <div className="mx-auto flex min-h-screen max-w-[68ch] flex-col gap-8 px-5 py-10">
      <ThemeSync />
      <header className="space-y-3">
        <Link href="/" className="text-[13px] text-blue-text hover:underline">
          ← Back to Trader
        </Link>
        <h1 className="text-[28px] font-semibold tracking-[-0.02em]">Privacy Policy</h1>
        <p className="text-[13px] text-text-muted">Last updated {LAST_UPDATED}.</p>
      </header>

      <main className="flex flex-col gap-6">
        <p className="text-[13px] leading-relaxed text-text-muted">
          Trader is a teaching demonstration: a simulated trading workstation built for a course on
          agentic AI coding. The money is imaginary, the portfolio is imaginary, and nothing here is
          financial advice. This page describes what the app stores anyway, because it does store
          something, and you should be able to find out what.
        </p>

        <Section title="What is stored if you never sign in">
          <p>
            Visiting the app creates an anonymous guest account. It is identified by a random id
            held in a single signed cookie named <code>trader_session</code>. That id is not
            derived from anything about you — it is not an advertising identifier, and it is not
            shared with anyone.
          </p>
          <p>Attached to that id, the app stores the work you do in it:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>your watchlist</li>
            <li>your positions, your cash balance, and the log of simulated trades behind them</li>
            <li>periodic snapshots of your portfolio&rsquo;s total value, which draw the P&amp;L chart</li>
            <li>the messages you exchange with the AI assistant</li>
            <li>when the account was created and when it was last used</li>
          </ul>
        </Section>

        <Section title="What signing in adds">
          <p>
            Signing in with Google or GitHub is optional, and exists for one reason: it attaches the
            guest portfolio you already have to an account, so it survives a change of browser. It
            grants no extra access to anything and unlocks no extra features.
          </p>
          <p>When you sign in, the app stores what the provider returns about you:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>your account id at that provider, and which provider it was</li>
            <li>your email address</li>
            <li>your display name and the URL of your avatar image</li>
          </ul>
          <p>
            No password ever reaches this app, and neither does anything else in your Google or
            GitHub account. Trader asks each provider only for your basic profile and email.
          </p>
        </Section>

        <Section title="Cookies">
          <p>
            One cookie, <code>trader_session</code>, which holds the signed id described above. It
            is what makes your portfolio still be yours on your next visit. There are no analytics
            cookies, no advertising cookies, and no third-party trackers on any page of this app.
          </p>
          <p>
            Two more short-lived cookies exist only during a sign-in, to carry the OAuth state and
            verifier that prove the round trip came back to the same browser that started it. They
            are discarded as soon as the sign-in completes.
          </p>
        </Section>

        <Section title="How long it is kept">
          <p>
            A guest account that goes unused for seven days is deleted outright, along with its
            watchlist, positions, trades, snapshots, and chat history. A signed-in account is kept
            until you ask for it to be deleted.
          </p>
        </Section>

        <Section title="Who else sees it">
          <p>The app runs on infrastructure operated by other companies, and they process data on its behalf:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              <strong className="font-medium text-text">Vercel</strong> hosts the deployment and
              routes requests to it.
            </li>
            <li>
              <strong className="font-medium text-text">Neon</strong> hosts the Postgres database
              everything above is stored in.
            </li>
            <li>
              <strong className="font-medium text-text">Google and GitHub</strong> see a sign-in
              request only if you choose to sign in with them.
            </li>
            <li>
              <strong className="font-medium text-text">OpenRouter</strong> would receive your chat
              messages if the live AI assistant were enabled. On this deployment it is not: the
              assistant runs in a deterministic mock mode, so chat messages are answered on the
              server and are never sent to any model provider.
            </li>
          </ul>
          <p>
            Nothing is sold, rented, or handed to advertisers. There is no profiling and no
            behavioural tracking.
          </p>
        </Section>

        <Section title="Deleting your data">
          <p>
            Signing out drops the session cookie; the next visit starts a fresh guest. To have an
            account and everything attached to it deleted, or to ask what is held about you, write
            to{" "}
            <a href={`mailto:${CONTACT}`} className="text-blue-text hover:underline">
              {CONTACT}
            </a>
            .
          </p>
        </Section>

        <Section title="Security, honestly stated">
          <p>
            This is a course project, not a commercial service. Anyone who has the URL can use it
            and be given their own guest portfolio; accounts are isolated from one another, but the
            app itself is open to the public and carries no access control. Please do not put
            anything sensitive into the chat panel — it is a demonstration, and it should be
            treated as one.
          </p>
        </Section>

        <Section title="Changes">
          <p>
            If this policy changes, the date at the top changes with it. The whole history of this
            page is public in the project&rsquo;s Git repository.
          </p>
        </Section>
      </main>

      <div className="mt-auto pt-4">
        <Footer />
      </div>
    </div>
  );
}
