"use client";

import { DEMO_DISABLED_MESSAGE, useIsDemo } from "./use-role";

/** Wraps a group of write controls. For the demo account every button, input and select inside is
 *  disabled (a disabled fieldset does that natively) and hovering explains why; for every other role
 *  it renders its children untouched. Links are not disabled by a fieldset, so a write control that is
 *  a link must point at a page that is itself gated. The API refuses the write either way. */
/** `when={false}` turns the gate off for a control that only writes in some states (a wizard's last step). */
export function DemoGate({ children, when = true }: { children: React.ReactNode; when?: boolean }) {
  const demo = useIsDemo();
  if (!demo || !when) return <>{children}</>;
  return (
    <fieldset disabled title={DEMO_DISABLED_MESSAGE} data-demo-disabled className="contents">
      {children}
    </fieldset>
  );
}
