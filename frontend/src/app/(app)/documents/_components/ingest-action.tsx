"use client";

import { Button, ButtonLink } from "@/components/ui";
import { DEMO_DISABLED_MESSAGE, RESOLVE_ROLES, useRole } from "@/components/use-role";

/** Ingest is a staff action (`ingest_document` in kairos.rego). Hidden for roles the API would refuse;
 *  shown disabled, with the reason, for the demo account. */
export function IngestDocumentAction() {
  const role = useRole();
  if (role === "demo") return <Button variant="primary" disabled title={DEMO_DISABLED_MESSAGE}>Ingest document</Button>;
  if (!RESOLVE_ROLES.includes(role)) return null;
  return <ButtonLink href="/documents/ingest" variant="primary">Ingest document</ButtonLink>;
}
