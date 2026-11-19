import { useEffect, useRef } from 'react';
import { Icon } from './Icon';
import { useI18n } from '../i18n';

export type ToastTone = 'success' | 'error' | 'info';

/** Optional action-button slot (reserved in review R18; unused this iteration) */
export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastMessage {
  id: number;
  message: string;
  tone: ToastTone;
  action?: ToastAction;
}

const TONE_STYLES: Record<ToastTone, string> = {
  success: 'border-success/25 bg-success-soft text-success-deep',
  error: 'border-danger/25 bg-danger-soft text-danger-deep',
  info: 'border-brand-200 bg-brand-50 text-brand-800',
};

const TONE_ICONS = {
  success: 'check',
  error: 'warning',
  info: 'info',
} as const;

const INFO_DURATION_MS = 4200;
/** Errors stay for ≥8s and include a close button (review R18) */
const ERROR_DURATION_MS = 8000;

/**
 * Global toast (review R18 upgrade): the container is interactive (no pointer-events-none);
 * errors get 8s + a close button + an optional action button; hovering pauses auto-dismiss
 * (remaining time is preserved). The auto-dismiss timer is managed inside the component;
 * Workspace only calls showToast / dismiss.
 */
export function Toast({
  toast,
  onDismiss,
}: {
  toast: ToastMessage | null;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  const timerRef = useRef<number | null>(null);
  const remainingRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  useEffect(() => {
    if (!toast) return;
    // A new message (increasing id) resets the timer; cleaned up on unmount/replacement
    const duration =
      toast.tone === 'error' ? ERROR_DURATION_MS : INFO_DURATION_MS;
    remainingRef.current = duration;
    startedAtRef.current = Date.now();
    const timer = window.setTimeout(onDismiss, duration);
    timerRef.current = timer;
    return () => {
      window.clearTimeout(timer);
      timerRef.current = null;
    };
  }, [toast, onDismiss]);

  /** Hover pause: stop the clock and record the remaining time */
  function pauseTimer() {
    if (!toast || timerRef.current === null) return;
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
    const elapsed = Date.now() - startedAtRef.current;
    remainingRef.current = Math.max(
      (remainingRef.current ?? 0) - elapsed,
      0,
    );
  }

  /** Leave resume: continue with the remaining time */
  function resumeTimer() {
    if (!toast || timerRef.current !== null) return;
    startedAtRef.current = Date.now();
    timerRef.current = window.setTimeout(
      onDismiss,
      remainingRef.current ?? 0,
    );
  }

  if (!toast) return null;
  return (
    <div
      className="fixed bottom-4 right-4 z-[60] max-w-[calc(100vw-2rem)]"
      role={toast.tone === 'error' ? 'alert' : 'status'}
      aria-live={toast.tone === 'error' ? 'assertive' : 'polite'}
      onMouseEnter={pauseTimer}
      onMouseLeave={resumeTimer}
    >
      <div
        className={`flex min-h-10 max-w-md items-center gap-2 rounded-lg border px-3.5 py-2 text-[13px] shadow-float animate-fade-up ${TONE_STYLES[toast.tone]}`}
      >
        <Icon name={TONE_ICONS[toast.tone]} size={14} className="shrink-0" />
        <span className="min-w-0 flex-1 break-words">{toast.message}</span>
        {toast.action && (
          <button
            type="button"
            onClick={toast.action.onClick}
            className="shrink-0 rounded-md px-1.5 py-0.5 text-[12px] font-medium underline underline-offset-2 transition-colors duration-150 hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60"
          >
            {toast.action.label}
          </button>
        )}
        {toast.tone === 'error' && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label={t('common.close')}
            title={t('common.close')}
            className="shrink-0 rounded-md p-0.5 transition-colors duration-150 hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60"
          >
            <Icon name="close" size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
