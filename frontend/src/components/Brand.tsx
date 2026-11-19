import { useI18n } from '../i18n';

interface BrandMarkProps {
  size?: number;
  className?: string;
}

/**
 * Clew brand mark: a tangled ball of thread plus a loose end trailing to the bottom-right.
 * Deep orange base (currentColor, following text-brand-* in context);
 * the ball uses two light-orange tones for intertwined depth, and the loose end's tip is "the source of the trace".
 */
export function BrandMark({ size = 34, className = '' }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <rect width="40" height="40" rx="11" fill="currentColor" />
      {/* The thread ball itself */}
      <circle cx="18.5" cy="18.5" r="9" stroke="#FB923C" strokeWidth="1.7" />
      {/* Intertwined arcs: two light and one dark, creating wrapping depth */}
      <path
        d="M10.2 16.8Q18.5 11.2 26.8 16.8"
        stroke="#FFEDD5"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M9.6 20.4Q18.5 26.2 27.4 20.4"
        stroke="#FFEDD5"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M13.4 11.4Q19.6 18.5 13.6 25.8"
        stroke="#FB923C"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      {/* Loose end: leads out of the ball; the tip is the source */}
      <path
        d="M26.2 24.6Q30.5 27.5 33 31.5"
        stroke="#FFEDD5"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="33.4" cy="32.4" r="1.7" fill="#FFEDD5" />
    </svg>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark size={compact ? 30 : 34} className="text-brand-800" />
      <div className="leading-none">
        <div className="font-sans text-base font-semibold tracking-tight text-ink">
          Clew<span className="text-brand-500">.</span>
        </div>
        {!compact && (
          <div className="mt-1 font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
            {t('brand.tagline')}
          </div>
        )}
      </div>
    </div>
  );
}
