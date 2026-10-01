import { describe, expect, it } from "vitest";
import nextConfig, { contentSecurityPolicy } from "../../next.config";

// L2
describe("security headers", () => {
  it("ships CSP, nosniff, referrer and permissions policies on every route", async () => {
    const [rule] = await nextConfig.headers!();
    const h = Object.fromEntries(rule.headers.map((x) => [x.key, x.value]));
    expect(rule.source).toBe("/:path*");
    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(h["Permissions-Policy"]).toContain("microphone=(self)");
    expect(h["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
  });

  it("allows only the API origin and the YouTube embed off-site", () => {
    const csp = contentSecurityPolicy("https://api.example.com/v1", false);
    expect(csp).toContain("connect-src 'self' https://api.example.com;");
    expect(csp).toContain("frame-src https://www.youtube-nocookie.com;");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).not.toContain("unsafe-eval");
  });

  it("allows eval only in development and survives a bad API url", () => {
    expect(contentSecurityPolicy("::nope", true)).toContain("'unsafe-eval'");
    expect(contentSecurityPolicy(undefined, false)).toContain("http://localhost:8000");
  });
});
