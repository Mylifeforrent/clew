import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';

/**
 * Overlay behavior foundation (review R13): every overlay layer plugs into this,
 * replacing the hand-written document keydown / Tab trap / focus save / body scroll
 * lock in each overlay.
 *
 * - Focus save/restore: record `document.activeElement` on open, restore on close/unmount;
 * - Tab containment: Tab / Shift+Tab cannot move focus out of the container (focus lost
 *   outside the container is pulled back in);
 * - Esc stack: a module-level overlay stack (last opened wins); only the top responds to Esc —
 *   when the AI drawer and the versions drawer are open together, one Esc closes only the
 *   most recent layer;
 * - body scroll lock: save the previous value and lock `body.style.overflow = 'hidden'` on
 *   open, restore in stack order on close/unmount (no stomping when multiple layers are open).
 *
 * `onRequestClose` / `dismissible` are read through internal refs: when the parent callback
 * is unstable, listeners are not re-attached and no stale closures appear; pass
 * `dismissible: false` in busy states to refuse closing.
 */

/** Focusable element selector (carried over from the original ImportWizardModal implementation, including summary). */
const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'summary',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

interface OverlayStackEntry {
  requestClose: () => void;
}

/** Module-level overlay stack: only the top entry (last pushed) responds to Esc and Tab containment. */
const overlayStack: OverlayStackEntry[] = [];

export interface OverlayBehaviorOptions {
  open: boolean;
  onRequestClose: () => void;
  /** When false (busy and other refusal states), Esc is swallowed and does not close; defaults to true. */
  dismissible?: boolean;
  /** Element to focus first on open (close button / input / cancel button); defaults to the first focusable element in the container. */
  initialFocusRef?: RefObject<HTMLElement | null>;
}

export function useOverlayBehavior(
  containerRef: RefObject<HTMLElement | null>,
  options: OverlayBehaviorOptions,
): void {
  const { open, onRequestClose, dismissible = true, initialFocusRef } = options;

  // Key callbacks are read through refs so a listener attached once while open still sees the latest values.
  const latestRef = useRef({ onRequestClose, dismissible });
  useEffect(() => {
    latestRef.current = { onRequestClose, dismissible };
  });

  const entryRef = useRef<OverlayStackEntry | null>(null);
  if (entryRef.current === null) {
    entryRef.current = {
      requestClose: () => latestRef.current.onRequestClose(),
    };
  }

  useEffect(() => {
    if (!open) return;
    const container = containerRef.current;
    const entry = entryRef.current;
    if (!container || !entry) return;

    const isTopOfStack = (): boolean =>
      overlayStack[overlayStack.length - 1] === entry;

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        // One Esc closes only the most recently opened layer (e.g. AI drawer + versions drawer open together)
        if (!isTopOfStack()) return;
        event.preventDefault();
        if (latestRef.current.dismissible) {
          latestRef.current.onRequestClose();
        }
        return;
      }
      if (event.key !== 'Tab' || !isTopOfStack()) return;
      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      // Focus already landed outside the container (background behind the mask): pull it back in; Shift+Tab enters from the end
      if (!active || !container.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey) {
        if (active === first || !focusable.includes(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !focusable.includes(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    overlayStack.push(entry);
    document.addEventListener('keydown', handleKeyDown);

    // Initial focus: prefer the designated element; if focus is already inside the container
    // (e.g. an autoFocus element), respect it; if the designated element is not focusable
    // (e.g. a disabled input), fall back to the first focusable element in the container.
    const activeNow =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    if (!activeNow || !container.contains(activeNow)) {
      const preferred = initialFocusRef?.current ?? null;
      if (preferred) preferred.focus();
      const focusedNow =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      if (!focusedNow || !container.contains(focusedNow)) {
        container.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();
      }
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      const index = overlayStack.indexOf(entry);
      if (index !== -1) overlayStack.splice(index, 1);
      document.body.style.overflow = previousOverflow;
      if (previousFocus && previousFocus.isConnected) {
        previousFocus.focus();
      }
    };
    // containerRef / initialFocusRef / entryRef are all caller useRefs with stable identity;
    // onRequestClose and dismissible are read via latestRef, so parent renders do not re-attach listeners.
  }, [open, containerRef, initialFocusRef, entryRef]);
}
