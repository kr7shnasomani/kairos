// Vault document list: every ingested source, active or superseded.
import Link from "next/link";
import { getDocuments, isForbidden } from "@/lib/api";
import { EmptyState, PageHeader } from "@/components/ui";
import { StatPills } from "@/components/stat-pills";
import { DocumentsTable } from "./_components/documents-table";
import { IngestDocumentAction } from "./_components/ingest-action";

const PAGE_SIZE = 100;

export default async function DocumentsPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const page = Math.max(1, Math.floor(Number((await searchParams).page)) || 1);
  const res = await getDocuments({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }).catch((e) => { if (isForbidden(e)) return null; throw e; });
  if (!res) return null;
  const { data } = res;
  const items = data.items ?? [];
  const total = data.total ?? items.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  // Pills describe the whole vault, not the page in view: one cheap count for the active share.
  const activeCount = (await getDocuments({ limit: 1, status: "active" }).catch(() => null))?.data.total
    ?? items.filter((d) => d.status === "active").length;

  return (
    <div data-testid="documents-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Documents"
        lede="The vault of every manual, bulletin, procedure, report and permit the system has read, each stored byte for byte with its authority level. Open one to see what was extracted from it, what relies on it, and its supersede history."
        actions={
          <>
            <Link
              href="/documents/compare"
              className="inline-flex h-9 items-center rounded-lg border border-line px-3.5 text-body font-semibold text-ink transition-colors hover:bg-surface-2"
            >
              Compare
            </Link>
            <IngestDocumentAction />
          </>
        }
      />

      <section data-testid="documents-summary" className="mt-5">
        <StatPills
          pills={[
            { key: "total", label: "Evidence records", value: total },
            { key: "active", label: "Active", value: activeCount },
            { key: "superseded", label: "Superseded", value: Math.max(0, total - activeCount) },
          ]}
        />
        {!!data.excluded_test_documents && (
          <p className="mt-2 text-caption text-muted">
            {data.excluded_test_documents} test-sweep document{data.excluded_test_documents === 1 ? "" : "s"} hidden — filtered from this view, never deleted.
          </p>
        )}
      </section>

      {items.length === 0 ? (
        <div className="mt-4">
          <EmptyState message="No documents ingested" action={{ label: "Ingest a document", href: "/documents/ingest" }} />
        </div>
      ) : (
        <>
          <DocumentsTable items={items} />
          {pages > 1 && (
            <nav aria-label="Document pages" className="mt-3 flex items-center justify-end gap-3 text-caption font-medium text-muted">
              {page > 1 && <Link href={`/documents?page=${page - 1}`} className="text-link hover:underline">Previous</Link>}
              <span className="tabular">Page {page} of {pages}</span>
              {page < pages && <Link href={`/documents?page=${page + 1}`} className="text-link hover:underline">Next</Link>}
            </nav>
          )}
        </>
      )}
    </div>
  );
}
