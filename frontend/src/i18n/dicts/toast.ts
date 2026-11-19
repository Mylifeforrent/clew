/** toast.* dictionary (populated when the corresponding component is migrated). */
export const zhToast = {} as const;

export type ToastKey = keyof typeof zhToast;

export const enToast: Record<ToastKey, string> = {};
