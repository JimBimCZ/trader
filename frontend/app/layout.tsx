import type { Metadata, Viewport } from "next";
import { THEME_STORAGE_KEY } from "@/lib/useTheme";
import { themeStyleSheet } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trader — AI Trading Workstation",
  description: "Live market data, a simulated portfolio, and an AI copilot.",
};

// Both appearances are declared, so Safari tints its own chrome to match.
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F2F2F7" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

/**
 * Resolves the appearance before the first paint. The pages are prerendered,
 * so without this a viewer in dark mode gets a white flash while React boots.
 * The theme store adopts what this decided rather than deciding again.
 */
const PREPAINT = `(function(){try{
var m=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)})||"system";
var d=m==="dark"||(m==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);
var r=document.documentElement;r.dataset.theme=d?"dark":"light";r.dataset.themeMode=m;
}catch(e){}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <style id="theme-tokens" dangerouslySetInnerHTML={{ __html: themeStyleSheet() }} />
        <script dangerouslySetInnerHTML={{ __html: PREPAINT }} />
      </head>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
