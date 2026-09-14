// Assets list — the canonical asset registry every piece of knowledge attaches to.
import { getAssets } from "@/lib/api";
import { label } from "@/lib/labels";
import { EmptyState, KpiGroup, PageHeader } from "@/components/ui";
import { AssetRegistry } from "./asset-registry";
import { IdentityConfirmAction, RegisterAssetAction } from "./identity-action";

export default async function AssetsPage() {
  const { data } = await getAssets();
  // Live-only: never render fixtures. A fallback means the backend is unreachable →
  // surface the shared error boundary (Try again) instead of fabricated assets.
  const items = data.items ?? [];

  // Spec §3: pills by equipment class — total plus the top classes by count.
  const byClass = new Map<string, number>();
  for (const a of items) byClass.set(a.equipment_class, (byClass.get(a.equipment_class) ?? 0) + 1);
  const classPills = [...byClass.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([label, value]) => ({ key: label, label, value }));

  return (
    <div data-testid="assets-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Asset-centric truth"
        title="Assets"
        lede="Every piece of knowledge orbits a canonical asset."
        actions={
          <>
            <RegisterAssetAction />
            <IdentityConfirmAction />
          </>
        }
      />

      <section data-testid="assets-summary" className="mt-5">
        <KpiGroup
          total={{ label: "Registered assets", value: data.total ?? items.length }}
          breakdownLabel="By equipment class"
          breakdown={classPills.map((p) => ({ label: label(p.label), value: p.value }))}
        />
      </section>

      {items.length === 0 ? (
        <div className="mt-4">
          <EmptyState message="No assets registered yet" action={{ label: "Register assets", href: "/assets/register" }} />
        </div>
      ) : (
        <AssetRegistry assets={items} />
      )}
    </div>
  );
}
