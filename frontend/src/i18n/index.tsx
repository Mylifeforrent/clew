import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { zh } from './zh';
import { en } from './en';

/** Supported locales. Defaults to en; no browser auto-detection (predictable behavior). zh stays selectable and the preference is persisted. */
export type Locale = 'zh' | 'en';

/** All message keys: the aggregated zh dictionary is the type baseline; en is locally constrained per dictionary module. */
export type MessageKey = keyof typeof zh;

export type TranslateParams = Record<string, string | number>;

/** t(key, params): {var} interpolation; plural semantics are handled by dictionary wording (e.g. `Fields · {count}`). */
export type TranslateFn = (
  key: MessageKey,
  params?: TranslateParams,
) => string;

const DICTS: Record<Locale, Partial<Record<MessageKey, string>>> = { zh, en };
const LOCALE_STORAGE_KEY = 'clew.locale';
const HTML_LANG: Record<Locale, string> = { zh: 'zh-CN', en: 'en' };
const DOCUMENT_TITLES: Record<Locale, string> = {
  zh: 'Clew · 字段级血缘',
  en: 'Clew · Field-level Data Lineage',
};

/** Static translation for non-React modules (e.g. lib/api.ts): follows the locale of the most recent Provider mount/switch. */
let activeLocale: Locale = 'en';

/** Non-React modules read the current locale (same source as tStatic; follows the most recent Provider mount/switch). */
export function getStaticLocale(): Locale {
  return activeLocale;
}

export function tStatic(key: MessageKey, params?: TranslateParams): string {
  const template = DICTS[activeLocale][key] ?? zh[key] ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

function readInitialLocale(): Locale {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored === 'zh' || stored === 'en') return stored;
  } catch {
    // Fall back to the default locale when localStorage is unavailable (private mode, etc.)
  }
  return 'en';
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: TranslateFn;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale);

  activeLocale = locale;

  useEffect(() => {
    document.documentElement.lang = HTML_LANG[locale];
    document.title = DOCUMENT_TITLES[locale];
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // A persistence failure does not affect switching in this session
    }
  }, []);

  const t = useCallback<TranslateFn>(
    (key, params) => {
      const template = DICTS[locale][key] ?? zh[key] ?? key;
      if (!params) return template;
      return template.replace(/\{(\w+)\}/g, (match, name: string) =>
        name in params ? String(params[name]) : match,
      );
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used within I18nProvider');
  return context;
}
