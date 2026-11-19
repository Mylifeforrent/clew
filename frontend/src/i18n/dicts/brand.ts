/** brand.* dictionary: brand wordmark tagline. */
export const zhBrand = {
  'brand.tagline': '字段级血缘 · 顺线溯源',
} as const;

export type BrandKey = keyof typeof zhBrand;

export const enBrand: Record<BrandKey, string> = {
  'brand.tagline': 'Field-level lineage · Follow the thread',
};
