import type { Metadata } from "next";
import { Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { CanvasTokensProvider } from "@/lib/graph-theme";
import { dmSans, instrumentSans } from "./landing-fonts";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Multi-script fallback for Hindi/Hinglish/Devanagari content (Layer 3)
const notoDevanagari = Noto_Sans_Devanagari({
  variable: "--font-noto-devanagari",
  subsets: ["devanagari"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Kairos",
  description:
    "The right knowledge to the right person at the moment of action. Governed industrial operational intelligence.",
  icons: { icon: "/logo.png", apple: "/logo.png" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="light"
      className={`${dmSans.variable} ${instrumentSans.variable} ${geistMono.variable} ${notoDevanagari.variable} h-full`}
      suppressHydrationWarning
    >
      <head>
        {/* Blocking on purpose: it sets data-theme before first paint, so the wrong palette never flashes. */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="/theme-init.js" />
      </head>
      <body className="min-h-full">
        <CanvasTokensProvider>{children}</CanvasTokensProvider>
      </body>
    </html>
  );
}
