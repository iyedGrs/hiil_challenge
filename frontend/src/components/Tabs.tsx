import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  panel: ReactNode;
}

interface TabsProps {
  tabs: TabItem[];
  idPrefix: string;
  /** Controlled active tab id (e.g. from a `?tab=` search param); omit for internal state. */
  activeId?: string;
  onActiveChange?: (id: string) => void;
}

/**
 * Accessible tab bar (roles/keyboard-nav per WAI-ARIA tabs pattern). Supports
 * an optional controlled `activeId` so a route can deep-link to a tab
 * (frontend.md FE-05: `?tab=documents&doc=...&page=...`).
 */
export function Tabs({ tabs, idPrefix, activeId, onActiveChange }: TabsProps) {
  const [internalIndex, setInternalIndex] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const controlledIndex = activeId !== undefined ? tabs.findIndex((t) => t.id === activeId) : -1;
  const activeIndex = controlledIndex >= 0 ? controlledIndex : internalIndex;

  function selectIndex(index: number, focus: boolean): void {
    const next = (index + tabs.length) % tabs.length;
    if (onActiveChange) onActiveChange(tabs[next].id);
    else setInternalIndex(next);
    if (focus) tabRefs.current[next]?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectIndex(index + 1, true);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectIndex(index - 1, true);
    } else if (event.key === "Home") {
      event.preventDefault();
      selectIndex(0, true);
    } else if (event.key === "End") {
      event.preventDefault();
      selectIndex(tabs.length - 1, true);
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
              onClick={() => selectIndex(index, false)}
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
