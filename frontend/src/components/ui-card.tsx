import { cn } from "@/lib/utils";

// Card family — the shared surface primitive (replaces the copy-pasted
// `rounded-xl border border-line bg-surface p-5` chrome). Plain divs, no
// client hooks, so it composes into server and client components alike.

export function Card({
  interactive = false,
  className,
  children,
}: {
  /** Landing hover (lp-card) for clickable cards (pair with an onClick/Link wrapper). */
  interactive?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "border border-line bg-surface",
        // The landing's lift: scale 1.02 + accent border, no floating shadow.
        interactive && "lp-card cursor-pointer",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("p-5 pb-0", className)}>{children}</div>;
}

export function CardTitle({ className, children }: { className?: string; children: React.ReactNode }) {
  return <h3 className={cn("text-body font-semibold text-ink", className)}>{children}</h3>;
}

export function CardDescription({ className, children }: { className?: string; children: React.ReactNode }) {
  return <p className={cn("mt-0.5 text-caption text-muted", className)}>{children}</p>;
}

export function CardContent({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("p-5", className)}>{children}</div>;
}

export function CardFooter({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("flex items-center gap-2 p-5 pt-0", className)}>{children}</div>;
}
