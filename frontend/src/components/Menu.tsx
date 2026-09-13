import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { DotsThreeVertical } from "@phosphor-icons/react";
import { IconButton } from "./Button";

export interface MenuAction {
  id: string;
  label: string;
  icon?: ReactNode;
  tone?: "default" | "danger";
  onSelect: () => void;
}

interface MenuProps {
  /** Names the menu for assistive tech, e.g. "Actions pour facture.pdf". */
  label: string;
  actions: MenuAction[];
  className?: string;
}

/**
 * Overflow menu (WAI-ARIA menu-button pattern): collapses a row of equally
 * weighted secondary controls into one affordance, so a document tile shows
 * its content instead of three competing buttons.
 */
export function Menu({ label, actions, className = "" }: MenuProps) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent): void {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close(refocus: boolean): void {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  }

  function openAndFocus(index: number): void {
    setOpen(true);
    window.setTimeout(() => itemRefs.current[index]?.focus(), 0);
  }

  function handleTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>): void {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openAndFocus(0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAndFocus(actions.length - 1);
    }
  }

  function handleItemKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      itemRefs.current[(index + 1) % actions.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      itemRefs.current[(index - 1 + actions.length) % actions.length]?.focus();
    } else if (event.key === "Tab") {
      close(false);
    }
  }

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <IconButton
        ref={triggerRef}
        label={label}
        icon={<DotsThreeVertical size={18} weight="bold" />}
        variant="secondary"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => (open ? close(false) : setOpen(true))}
        onKeyDown={handleTriggerKeyDown}
      />
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          className="absolute end-0 top-full z-20 mt-1 min-w-44 overflow-hidden rounded-md border border-border bg-surface py-1 shadow-overlay animate-enter-up"
        >
          {actions.map((action, index) => (
            <button
              key={action.id}
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              type="button"
              role="menuitem"
              onClick={() => {
                close(false);
                action.onSelect();
              }}
              onKeyDown={(e) => handleItemKeyDown(e, index)}
              className={`flex w-full items-center gap-2 px-3 py-2 text-start text-sm transition-colors ${
                action.tone === "danger"
                  ? "text-danger hover:bg-danger-bg"
                  : "text-text hover:bg-surface-muted"
              }`}
            >
              {action.icon && (
                <span aria-hidden="true" className="shrink-0">
                  {action.icon}
                </span>
              )}
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
