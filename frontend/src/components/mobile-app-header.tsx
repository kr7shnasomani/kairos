import { Icon } from "@/components/icon";
type MobileAppHeaderProps = {
  onOpenMenu: () => void;
  onOpenSearch: () => void;
  onCreate: () => void;
  onOpenUser: () => void;
  userInitial: string;
};

export function MobileAppHeader({ onOpenMenu, onOpenSearch, onCreate, onOpenUser, userInitial }: MobileAppHeaderProps) {
  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-1.5 border-b border-line bg-surface px-2 shadow-sm sm:gap-3 sm:px-4 lg:hidden print:hidden">
      <button type="button" onClick={onOpenMenu} aria-label="Open menu" className="grid size-10 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        <Icon name="list" className="size-5" />
      </button>
      <button type="button" onClick={onOpenSearch} aria-label="Search workspace" className="flex h-10 min-w-10 flex-1 items-center gap-2 overflow-hidden rounded-lg border border-line bg-page px-2 text-sm text-muted shadow-sm transition-colors hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] hover:text-ink sm:h-11 sm:min-w-0 sm:rounded-xl sm:px-3">
        <Icon name="magnifying-glass" className="size-4 shrink-0" />
        <span className="min-w-0 truncate">Search…</span>
      </button>
      <button type="button" onClick={onCreate} aria-label="Ingest document" className="fill-sweep grid size-10 shrink-0 place-items-center bg-accent text-on-accent sm:size-11"><Icon name="plus" className="relative z-10 size-5" /></button>
      <button type="button" onClick={onOpenUser} aria-label="Open user menu" className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-2 text-label font-bold text-muted">{userInitial}</button>
    </header>
  );
}
