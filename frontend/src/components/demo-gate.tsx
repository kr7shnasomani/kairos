"use client";

import { DEMO_DISABLED_MESSAGE, useIsDemo } from "./use-role";

/** Wraps the few controls the demo account cannot use (the model gate run, the provider probes). For
 *  the demo account every button, input and select inside is disabled (a disabled fieldset does that
 *  natively) and hovering explains why; for every other role it renders its children untouched.
 *  Every other action works for the demo account, on showcase data only. The API refuses the call
 *  either way. */
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
