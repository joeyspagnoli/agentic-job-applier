/**
 * @packageDocumentation
 *
 * Global command bar (Cmd+K / Ctrl+K) for quick navigation and actions.
 *
 * @remarks
 * Renders a modal overlay with a search input and filtered action list.
 * Supports fuzzy (case-insensitive substring) filtering, keyboard navigation
 * (Up/Down/Enter/Escape), and click-to-execute. Clicking the backdrop closes
 * the bar.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Briefcase,
  Eye,
  AlertCircle,
  CreditCard,
  Settings,
  Play,
  Download,
  Search,
  Command,
  type LucideIcon,
} from "lucide-react";
import {
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE,
  COLOR_SURFACE_CONTAINER_LOW,
  Z_COMMAND_BAR,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single action rendered in the command list. */
interface CommandAction {
  /** Unique identifier passed to `onAction`. */
  id: string;
  /** Human-readable label displayed in the list. */
  label: string;
  /** Lucide icon component rendered beside the label. */
  icon: LucideIcon;
  /** Optional grouping category (e.g. "Navigate", "Quick Actions"). */
  group: string;
  /** Callback executed when the action is selected. */
  execute: () => void;
}

/** Props accepted by the {@link CommandBar} component. */
export interface CommandBarProps {
  /** Whether the command bar is currently visible. */
  open: boolean;
  /** Callback to close the command bar. */
  onClose: () => void;
  /** Optional callback invoked with the action id when an action executes. */
  onAction?: (actionId: string) => void;
}

/** Return type of the {@link useCommandBar} hook. */
export interface UseCommandBarReturn {
  /** Whether the command bar is open. */
  open: boolean;
  /** Setter for the open state. */
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  /** Toggle the command bar open/closed. */
  toggle: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Registers a global Cmd+K / Ctrl+K listener and manages open state.
 *
 * @returns Object containing `open`, `setOpen`, and `toggle`.
 */
export function useCommandBar(): UseCommandBarReturn {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  useEffect(() => {
    /**
     * Handles global keydown to open/close the command bar.
     *
     * @param e - The keyboard event.
     */
    function handleKeyDown(e: KeyboardEvent): void {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        toggle();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggle]);

  return { open, setOpen, toggle };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Modal command bar overlay for quick navigation and actions.
 *
 * @param props - {@link CommandBarProps}
 * @returns The command bar JSX, or `null` when closed.
 */
export function CommandBar({
  open,
  onClose,
  onAction,
}: CommandBarProps): JSX.Element | null {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Build the list of available actions.
  const actions: CommandAction[] = useMemo(
    () => [
      {
        id: "nav-dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        group: "Navigate",
        execute: () => navigate("/"),
      },
      {
        id: "nav-jobs",
        label: "Jobs",
        icon: Briefcase,
        group: "Navigate",
        execute: () => navigate("/jobs"),
      },
      {
        id: "nav-human-review",
        label: "Human Review",
        icon: Eye,
        group: "Navigate",
        execute: () => navigate("/human-review"),
      },
      {
        id: "nav-failures",
        label: "Failures",
        icon: AlertCircle,
        group: "Navigate",
        execute: () => navigate("/failures"),
      },
      {
        id: "nav-cost-tracking",
        label: "Cost Tracking",
        icon: CreditCard,
        group: "Navigate",
        execute: () => navigate("/cost-tracking"),
      },
      {
        id: "nav-settings",
        label: "Settings",
        icon: Settings,
        group: "Navigate",
        execute: () => navigate("/settings"),
      },
      {
        id: "action-start-pipeline",
        label: "Start pipeline run",
        icon: Play,
        group: "Quick Actions",
        execute: () => {
          /* placeholder — wired up by onAction */
        },
      },
      {
        id: "action-import-job",
        label: "Import job",
        icon: Download,
        group: "Quick Actions",
        execute: () => {
          /* placeholder — wired up by onAction */
        },
      },
      {
        id: "action-search-jobs",
        label: "Search jobs",
        icon: Search,
        group: "Quick Actions",
        execute: () => navigate("/jobs"),
      },
    ],
    [navigate],
  );

  // Filter actions by query (case-insensitive substring).
  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    const lower = query.toLowerCase();
    return actions.filter((a) => a.label.toLowerCase().includes(lower));
  }, [actions, query]);

  // Reset state when opening/closing.
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      // Focus the input on next frame so the element is mounted.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Clamp selection when the filtered list shrinks.
  useEffect(() => {
    setSelectedIndex((prev) => Math.min(prev, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  // Scroll the selected item into view.
  useEffect(() => {
    if (!listRef.current) return;
    const item = listRef.current.children[selectedIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  /**
   * Executes the action at the given index and closes the bar.
   *
   * @param index - Index into the `filtered` array.
   */
  const executeAction = useCallback(
    (index: number) => {
      const action = filtered[index];
      if (!action) return;
      action.execute();
      onAction?.(action.id);
      onClose();
    },
    [filtered, onAction, onClose],
  );

  /**
   * Handles keyboard navigation inside the command bar.
   *
   * @param e - The keyboard event from the input.
   */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) => (prev + 1) % Math.max(1, filtered.length));
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex(
            (prev) => (prev - 1 + filtered.length) % Math.max(1, filtered.length),
          );
          break;
        case "Enter":
          e.preventDefault();
          executeAction(selectedIndex);
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
      }
    },
    [filtered.length, selectedIndex, executeAction, onClose],
  );

  if (!open) return null;

  // Group filtered actions by category for rendering.
  const groups = new Map<string, CommandAction[]>();
  for (const action of filtered) {
    const list = groups.get(action.group) ?? [];
    list.push(action);
    groups.set(action.group, list);
  }

  // Build a flat index map so we can highlight the selected row.
  let flatIndex = 0;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="animate-fade-in"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: Z_COMMAND_BAR,
          backgroundColor: "rgba(42, 36, 56, 0.35)",
        }}
      />

      {/* Panel */}
      <div
        className="animate-fade-in"
        style={{
          position: "fixed",
          top: "20%",
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: Z_COMMAND_BAR + 1,
          width: "min(560px, 90vw)",
          borderRadius: 16,
          backgroundColor: COLOR_SURFACE,
          border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
          boxShadow: "0 24px 64px rgba(42, 36, 56, 0.18)",
          overflow: "hidden",
          fontFamily: "'Plus Jakarta Sans', sans-serif",
        }}
      >
        {/* Search input */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "14px 18px",
            borderBottom: `1px solid ${COLOR_OUTLINE_VARIANT}`,
          }}
        >
          <Search size={18} color={COLOR_ON_SURFACE_VARIANT} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or search..."
            style={{
              flex: 1,
              border: "none",
              outline: "none",
              background: "transparent",
              fontSize: 15,
              color: COLOR_ON_SURFACE,
              fontFamily: "inherit",
            }}
          />
          <kbd
            style={{
              fontSize: 11,
              padding: "2px 6px",
              borderRadius: 6,
              backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
              border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
              color: COLOR_ON_SURFACE_VARIANT,
              fontFamily: "inherit",
              display: "flex",
              alignItems: "center",
              gap: 2,
            }}
          >
            <Command size={11} /> K
          </kbd>
        </div>

        {/* Action list */}
        <div
          ref={listRef}
          style={{
            maxHeight: 340,
            overflowY: "auto",
            padding: "6px 0",
          }}
        >
          {filtered.length === 0 && (
            <div
              style={{
                padding: "24px 18px",
                textAlign: "center",
                color: COLOR_ON_SURFACE_VARIANT,
                fontSize: 14,
              }}
            >
              No results found
            </div>
          )}

          {Array.from(groups.entries()).map(([groupName, items]) => (
            <div key={groupName}>
              <div
                style={{
                  padding: "8px 18px 4px",
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: COLOR_ON_SURFACE_VARIANT,
                }}
              >
                {groupName}
              </div>
              {items.map((action) => {
                const idx = flatIndex++;
                const isSelected = idx === selectedIndex;
                const Icon = action.icon;
                return (
                  <button
                    key={action.id}
                    onClick={() => executeAction(idx)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      width: "100%",
                      padding: "10px 18px",
                      border: "none",
                      cursor: "pointer",
                      fontSize: 14,
                      fontFamily: "inherit",
                      textAlign: "left",
                      borderRadius: 0,
                      color: isSelected ? COLOR_PRIMARY : COLOR_ON_SURFACE,
                      backgroundColor: isSelected
                        ? COLOR_PRIMARY_FIXED
                        : "transparent",
                      transition: "background-color 120ms ease, color 120ms ease",
                    }}
                  >
                    <Icon size={16} strokeWidth={2} />
                    <span>{action.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Fade-in animation */}
      <style>{`
        @keyframes commandBarFadeIn {
          from { opacity: 0; transform: translateX(-50%) translateY(8px) scale(0.98); }
          to   { opacity: 1; transform: translateX(-50%) translateY(0) scale(1); }
        }
        .animate-fade-in {
          animation: commandBarFadeIn 150ms ease-out both;
        }
      `}</style>
    </>
  );
}
