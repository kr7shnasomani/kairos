"use client";

import { ButtonLink } from "@/components/ui";
import { RESOLVE_ROLES, useRole, visibleTo } from "@/components/use-role";

/** Ingest is a staff action (`ingest_document` in kairos.rego). Hidden for roles the API would refuse;
 *  the demo account ingests into the showcase plant. */
export function IngestDocumentAction() {
  const role = useRole();
  if (!visibleTo(RESOLVE_ROLES, role)) return null;
  return <ButtonLink href="/documents/ingest" variant="primary">Ingest document</ButtonLink>;
}
