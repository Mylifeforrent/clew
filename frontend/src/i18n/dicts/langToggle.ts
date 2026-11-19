/** langToggle.* dictionary. */
export const zhLangToggle = {
  'langToggle.label': '切换语言',
  // Language names use their native form (identical in both locales) so the selector self-identifies
  'langToggle.zhName': '中文',
  'langToggle.enName': 'English',
} as const;

export type LangToggleKey = keyof typeof zhLangToggle;

export const enLangToggle: Record<LangToggleKey, string> = {
  'langToggle.label': 'Switch language',
  'langToggle.zhName': '中文',
  'langToggle.enName': 'English',
};
