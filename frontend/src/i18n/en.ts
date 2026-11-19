/**
 * English aggregate dictionary (the default locale).
 *
 * Each module's en export is locally constrained with `Record<XxxKey, string>`
 * (enforced at compile time to match the zh keys); after aggregation the whole object
 * is asserted back to MessageKey (compatible even when an empty module's keyof is never).
 */
import type { MessageKey } from './index';
import { enCommon } from './dicts/common';
import { enApp } from './dicts/app';
import { enToast } from './dicts/toast';
import { enBrand } from './dicts/brand';
import { enSourceBadge } from './dicts/sourceBadge';
import { enGroupNode } from './dicts/groupNode';
import { enDatasetNode } from './dicts/datasetNode';
import { enLineageEdge } from './dicts/lineageEdge';
import { enConfirmDialog } from './dicts/confirmDialog';
import { enTopbar } from './dicts/topbar';
import { enLogin } from './dicts/login';
import { enWorkspace } from './dicts/workspace';
import { enSidebar } from './dicts/sidebar';
import { enHistory } from './dicts/history';
import { enUserMgmt } from './dicts/userMgmt';
import { enVersion } from './dicts/version';
import { enEdgeDetail } from './dicts/edgeDetail';
import { enCanvas } from './dicts/canvas';
import { enPreview } from './dicts/preview';
import { enAi } from './dicts/ai';
import { enDetail } from './dicts/detail';
import { enImportWiz } from './dicts/importWiz';
import { enEdgeCreate } from './dicts/edgeCreate';
import { enAnnotation } from './dicts/annotation';
import { enFormat } from './dicts/format';
import { enApi } from './dicts/api';
import { enLangToggle } from './dicts/langToggle';

export const en: Partial<Record<MessageKey, string>> = {
  ...enCommon,
  ...enApp,
  ...enToast,
  ...enBrand,
  ...enSourceBadge,
  ...enGroupNode,
  ...enDatasetNode,
  ...enLineageEdge,
  ...enConfirmDialog,
  ...enTopbar,
  ...enLogin,
  ...enWorkspace,
  ...enSidebar,
  ...enHistory,
  ...enUserMgmt,
  ...enVersion,
  ...enEdgeDetail,
  ...enCanvas,
  ...enPreview,
  ...enAi,
  ...enDetail,
  ...enImportWiz,
  ...enEdgeCreate,
  ...enAnnotation,
  ...enFormat,
  ...enApi,
  ...enLangToggle,
};
