// Briefs inbox — proactive knowledge briefs delivered at the moment of action.
import { getBriefs } from "@/lib/api";
import { BriefInbox } from "@/components/brief-inbox";
import { PageHeader } from "@/components/ui";

export default async function BriefsPage() {
  const { data } = await getBriefs();
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Briefs"
        lede="Knowledge pushed to you at the moment you need it, before you think to ask: permits that need a signature, alarms, and work orders with the manual, bulletin and history behind them. Routine briefs are paced so you are never flooded."
      />

      <div className="mt-6">
        <BriefInbox response={data} />
      </div>
    </div>
  );
}
