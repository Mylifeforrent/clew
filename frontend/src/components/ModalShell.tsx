import { useRef } from 'react';
import type { ComponentProps, ReactNode, RefObject } from 'react';
import { Icon } from './Icon';
import type { IconName } from './Icon';
import { useOverlayBehavior } from '../lib/useOverlayBehavior';

/**
 * Unified overlay shell (review R13): mask + card container + header (icon badge/title/close button)
 * + body + footer slots; behavior (Esc stack protocol, Tab containment, focus save/restore,
 * body scroll lock) is provided internally by useOverlayBehavior, so callers no longer hand-write it.
 *
 * Style conventions (hifi 00 §7.6/§7.7, zero-visual-change migration):
 * - Base classes are fixed: mask z (modal 50 / drawer 40), card radius/border/shadow/enter animation;
 * - Width tiers, max-h, flex-col, etc. are appended via `className`; mask padding via `overlayClassName`;
 * - When `bodyClassName` / `footerClassName` / `titleClassName` are provided they **replace** the
 *   default classes (avoiding Tailwind same-property conflicts); otherwise defaults apply;
 * - Complex headers (composite row above the eyebrow / badge inside the title row) are fully taken
 *   over via `titleNode`;
 *   ConfirmDialog's "badge + title + body in one block, no close button" is fully taken over via `header`.
 */

const MODAL_OVERLAY_CLASS =
  'fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 animate-fade-in';
const DRAWER_OVERLAY_CLASS =
  'fixed inset-0 z-40 flex justify-end bg-slate-900/25 animate-fade-in';

const MODAL_CARD_CLASS =
  'relative z-[51] mx-auto w-full overflow-hidden rounded-xl border border-line bg-card shadow-modal animate-modal-in';
const DRAWER_CARD_CLASS =
  'relative z-[41] flex h-full w-full flex-col overflow-hidden border-l border-line bg-card shadow-float animate-drawer-in';

const HEADER_CLASS =
  'flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line-soft px-4';
const DEFAULT_BADGE_CLASS =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-brand-200 bg-brand-50 text-brand-700';
const EYEBROW_CLASS =
  'font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint';
const CLOSE_BUTTON_CLASS =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50';
const DEFAULT_BODY_CLASS = 'min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4';
const DEFAULT_FOOTER_CLASS =
  'flex h-12 shrink-0 items-center justify-end gap-2 border-t border-line-soft px-4';

export interface ModalShellProps {
  /** modal = centered card (z-50); drawer = right-side sliding drawer (z-40). */
  variant: 'modal' | 'drawer';
  open: boolean;
  /** Title text; when titleNode / header take over it remains the required contract value and aria fallback. */
  title: string;
  /** Title element id: the aria-labelledby target; must match when titleNode supplies its own title element. */
  titleId: string;
  /** Header icon badge icon (following the existing 8×8 brand badge style). */
  titleIcon?: IconName;
  /** Badge override class (the AI drawer passes its full badge class for the ai-colored badge). */
  badgeClassName?: string;
  /** Small mono line above the title (EdgeCreate / UserManagement / History). */
  eyebrow?: ReactNode;
  /** Custom title node (must contain a title element with id={titleId}): ImportWizard / Preview / AI. */
  titleNode?: ReactNode;
  /** Title element override class (e.g. History's mono 13px title). */
  titleClassName?: string;
  /** Actions on the header's right side, left of the close button (refresh, copy locator, etc.). */
  headerExtra?: ReactNode;
  /** Strip between header and body (import wizard step indicator, AI focus strip/status banner). */
  subHeader?: ReactNode;
  /** Full custom replacement of the header (ConfirmDialog: badge + title + body in one block, no close button). */
  header?: ReactNode;
  onRequestClose: () => void;
  /** Pass false in busy refusal states: Esc / mask / close button all refuse closing; defaults to true. */
  dismissable?: boolean;
  children?: ReactNode;
  footer?: ReactNode;
  /** Extra classes for the card container (width tiers, max-h-[85vh] flex flex-col, etc.). */
  className?: string;
  /** Extra classes for the mask (modal padding p-3 sm:p-6 / p-4). */
  overlayClassName?: string;
  /** body container classes: when provided they replace the defaults. */
  bodyClassName?: string;
  /** Props forwarded to the body container (AI drawer's list ref / role=log / aria-live / aria-label). */
  bodyProps?: ComponentProps<'div'>;
  /** footer container classes: when provided they replace the defaults. */
  footerClassName?: string;
  /** Close button aria-label (reusing each overlay's existing i18n key); when omitted no close button renders. */
  closeLabel?: string;
  /** Card role; ConfirmDialog uses 'alertdialog'; defaults to 'dialog'. */
  role?: 'dialog' | 'alertdialog';
  /** Element to focus first on open; defaults to the close button (the AI drawer passes the input, ConfirmDialog the cancel button). */
  initialFocusRef?: RefObject<HTMLElement | null>;
}

export function ModalShell({
  variant,
  open,
  title,
  titleId,
  titleIcon,
  badgeClassName,
  eyebrow,
  titleNode,
  titleClassName,
  headerExtra,
  subHeader,
  header: customHeader,
  onRequestClose,
  dismissable = true,
  children,
  footer,
  className,
  overlayClassName,
  bodyClassName,
  bodyProps,
  footerClassName,
  closeLabel,
  role = 'dialog',
  initialFocusRef,
}: ModalShellProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const { ref: bodyRef, ...bodyRest } = bodyProps ?? {};

  useOverlayBehavior(containerRef, {
    open,
    onRequestClose,
    dismissible: dismissable,
    initialFocusRef:
      initialFocusRef ?? (closeLabel !== undefined ? closeButtonRef : undefined),
  });

  if (!open) return null;

  const overlayClass =
    variant === 'modal' ? MODAL_OVERLAY_CLASS : DRAWER_OVERLAY_CLASS;
  const cardClass =
    variant === 'modal' ? MODAL_CARD_CLASS : DRAWER_CARD_CLASS;

  return (
    <div
      className={overlayClassName ? `${overlayClass} ${overlayClassName}` : overlayClass}
      onMouseDown={(event) => {
        // Only the mask itself (not bubbled events from inside the card) triggers; busy refusal states do not respond
        if (event.target === event.currentTarget && dismissable) {
          onRequestClose();
        }
      }}
    >
      <div
        ref={containerRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        className={className ? `${cardClass} ${className}` : cardClass}
      >
        {customHeader ?? (
          <header className={HEADER_CLASS}>
            <div className="flex min-w-0 items-center gap-2.5">
              {titleIcon && (
                <span className={badgeClassName ?? DEFAULT_BADGE_CLASS}>
                  <Icon name={titleIcon} size={16} />
                </span>
              )}
              {eyebrow !== undefined ? (
                <div className="min-w-0">
                  <div className={EYEBROW_CLASS}>{eyebrow}</div>
                  <h2
                    id={titleId}
                    className={titleClassName ?? 'mt-0.5 text-[14px] font-semibold text-ink'}
                  >
                    {title}
                  </h2>
                </div>
              ) : (
                (titleNode ?? (
                  <h2
                    id={titleId}
                    className={titleClassName ?? 'min-w-0 text-[14px] font-semibold text-ink'}
                  >
                    {title}
                  </h2>
                ))
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {headerExtra}
              {closeLabel !== undefined && (
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={onRequestClose}
                  disabled={!dismissable}
                  className={CLOSE_BUTTON_CLASS}
                  aria-label={closeLabel}
                >
                  <Icon name="close" size={16} />
                </button>
              )}
            </div>
          </header>
        )}

        {subHeader}

        {children != null && (
          <div
            ref={bodyRef}
            {...bodyRest}
            className={bodyClassName ?? DEFAULT_BODY_CLASS}
          >
            {children}
          </div>
        )}

        {footer != null && (
          <footer className={footerClassName ?? DEFAULT_FOOTER_CLASS}>
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
