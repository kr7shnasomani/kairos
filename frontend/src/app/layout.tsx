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

// Apply saved theme, contrast and devtools state before paint to avoid a flash.
const themeInit = `(function(){try{var t=localStorage.getItem('kairos-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);var c=localStorage.getItem('kairos-contrast');if(c==='high')document.documentElement.setAttribute('data-contrast','high');var d=localStorage.getItem('kairos-devtools');if(d==='show')document.documentElement.setAttribute('data-devtools','show');}catch(e){}})();`;

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
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="min-h-full">
        <CanvasTokensProvider>{children}</CanvasTokensProvider>
      </body>
    </html>
  );
}
