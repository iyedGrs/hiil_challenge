import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  panel: ReactNode;
}

interface TabsProps {
  tabs: TabItem[];
  idPrefix: string;
}

/**
 * Accessible tab bar skeleton (workspace tabs land in a later PR — this is the
 * roles/keyboard-nav shell, per frontend.md F4 "Documents, Checks, Activity, Submit").
 */
export function Tabs({ tabs, idPrefix }: TabsProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function focusTab(index: number): void {
    const next = (index + tabs.length) % tabs.length;
    setActiveIndex(next);
    tabRefs.current[next]?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTab(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTab(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusTab(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusTab(tabs.length - 1);
    }
  }

  return (
    <div>
      <div role="tablist" aria-label="Sections du dossier" className="flex gap-1 border-b border-border">
        {tabs.map((tab, index) => {
          const selected = index === activeIndex;
          const tabId = `${idPrefix}-tab-${tab.id}`;
          const panelId = `${idPrefix}-panel-${tab.id}`;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              id={tabId}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveIndex(index)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
                selected ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab, index) => {
        const selected = index === activeIndex;
        const tabId = `${idPrefix}-tab-${tab.id}`;
        const panelId = `${idPrefix}-panel-${tab.id}`;
        return (
          <div key={tab.id} id={panelId} role="tabpanel" aria-labelledby={tabId} hidden={!selected} className="py-4">
            {tab.panel}
          </div>
        );
      })}
    </div>
  );
}
