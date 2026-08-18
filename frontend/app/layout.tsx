import type { Metadata } from "next";
import { Figtree, Inter } from "next/font/google";
import "./globals.css";

// Both faces are downloaded at build time and self-hosted in the export, so
// the container never reaches out to a font CDN at runtime.
const display = Figtree({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-display",
  display: "swap",
});

const body = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Trader — AI Trading Workstation",
  description: "Live market data, a simulated portfolio, and an AI copilot.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
