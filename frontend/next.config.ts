import type { NextConfig } from "next";

// The one cross-origin host the browser talks to is the API (NEXT_PUBLIC_API_URL, baked in at build).
function apiOrigin(apiUrl: string | undefined): string {
  try {
    return new URL(apiUrl ?? "http://localhost:8000").origin;
  } catch {
    return "http://localhost:8000";
  }
}

/** Content-Security-Policy. `script-src` keeps 'unsafe-inline' on purpose: Next 16 emits inline
 *  bootstrap and RSC-payload scripts on every page, so a hash cannot cover them, and a nonce would
 *  need per-request rendering, which turns the static landing page and every cached shell dynamic.
 *  The rest is tight: no plugins, no foreign frames, no off-site form posts, and only the API,
 *  YouTube's cookie-less embed and self-hosted fonts are reachable. */
export function contentSecurityPolicy(apiUrl: string | undefined, dev = false): string {
  const api = apiOrigin(apiUrl);
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "media-src 'self' blob:",
    `connect-src 'self' ${api}`,
    "frame-src https://www.youtube-nocookie.com",
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

const nextConfig: NextConfig = {
  // Emit a self-contained production server (.next/standalone/server.js)
  // for a minimal, non-root Docker runtime image. No effect on `next dev`.
  output: "standalone",

  // The dev-tools overlay defaults to a Next.js logo pinned bottom-left, which
  // lands inside every screenshot tools/capture_landing_shots.sh takes for the
  // landing page. Dev-only overlay, so this has no effect on the production build.
  devIndicators: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: contentSecurityPolicy(process.env.NEXT_PUBLIC_API_URL, process.env.NODE_ENV !== "production"),
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Voice notes need the microphone on this origin only; nothing else is used.
          { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=(), payment=(), usb=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
