"use client";

import { PageHeader } from "@/components/ui";
import { SystemTabs } from "@/components/system-tabs";
import { ThemeToggle, ContrastToggle } from "@/components/theme-toggle";

export default function SettingsPage() {
  return (
    <div data-testid="settings-workspace" className="mx-auto max-w-[1400px]">
      <SystemTabs />
      <PageHeader
        title="System Settings"
        lede="Tune how Kairos looks on this device: theme and contrast. These are stored in this browser, so they follow the device and not your account."
      />

      {/* One hairline panel: section list and content share a border, no floating gap. */}
      <div data-testid="settings-layout" className="mesh mt-8 items-stretch md:grid-cols-[220px_minmax(0,1fr)]">
      <nav data-testid="settings-navigation" aria-label="Preference sections" className="flex flex-col bg-surface-2 py-2">
        <span className="flex min-h-11 items-center bg-surface px-5 text-body font-semibold text-ink shadow-[inset_2px_0_0_var(--accent)]">Appearance</span>
        <span className="flex min-h-11 items-center px-5 text-body text-muted">Notifications</span>
        <span className="flex min-h-11 items-center px-5 text-body text-muted">Accessibility</span>
        <p className="mt-auto border-t border-line px-5 pt-3 text-caption text-muted">Additional preferences will appear here as account-level controls become available.</p>
      </nav>

      <section data-testid="settings-panel" className="bg-surface p-5 sm:p-8">
        <h2 className="font-display text-title font-medium text-ink">Display</h2>
        <p className="mt-1 text-caption text-muted">Tune this browser for your working environment.</p>
        <div className="mt-1 divide-y divide-line">
          <div className="flex min-h-11 items-center justify-between gap-4 py-4">
            <div>
              <p className="text-body font-medium">Theme</p>
              <p className="mt-0.5 text-caption text-muted">
                Light or dark palette. Colors only — layout and graph structure never change.
              </p>
            </div>
            <ThemeToggle />
          </div>
          <div className="flex min-h-11 items-center justify-between gap-4 py-4">
            <div>
              <p className="text-body font-medium">High contrast</p>
              <p className="mt-0.5 text-caption text-muted">
                Stronger borders and text for bright field conditions or low-visibility screens.
              </p>
            </div>
            <ContrastToggle />
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}
