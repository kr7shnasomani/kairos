// Briefs inbox — proactive knowledge briefs delivered at the moment of action.
import { getBriefs } from "@/lib/api";
import { BriefInbox } from "@/components/brief-inbox";
import { PageHeader } from "@/components/ui";

export default async function BriefsPage() {
  const { data } = await getBriefs();
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Proactive delivery"
        title="Briefs"
        lede="Knowledge delivered at the moment of action, before you had to ask."
      />

      <div className="mt-6">
        <BriefInbox response={data} />
      </div>
    </div>
  );
}
