import Link from "next/link";

export function BrandLink({ size = 30, href = "/" }: { size?: number; href?: string }) {
  return (
    <Link href={href} aria-label="Kairos home" className="flex items-center gap-2.5 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="Kairos" width={size} height={size} className="rounded-lg object-cover" style={{ width: size, height: size }} />
      <span className="rail-label text-subtitle font-semibold tracking-tight">Kairos</span>
    </Link>
  );
}
