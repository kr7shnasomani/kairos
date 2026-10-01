"use client";

import { ButtonLink } from "@/components/ui";
import { RESOLVE_ROLES, useRole } from "@/components/use-role";

/** Ingest is a staff action (`ingest_document` in kairos.rego); hidden for roles the API would refuse. */
export function IngestDocumentAction() {
  const role = useRole();
  if (!RESOLVE_ROLES.includes(role)) return null;
  return <ButtonLink href="/documents/ingest" variant="primary">Ingest document</ButtonLink>;
}
