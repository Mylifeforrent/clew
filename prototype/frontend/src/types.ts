export interface Session {
  access_token: string;
  token_type: string;
  username: string;
  role: string;
}

export interface LoginResponse extends Session {}

export interface DatasetSummary {
  id: string;
  name: string;
  field_count: number;
  field_names: string[];
}

export interface SourceFileRef {
  id: number;
  original_name: string;
}

export interface PreviewFileRef extends SourceFileRef {
  sha256: string;
  size_bytes: number | null;
  src_type: string;
  uploaded_by: string;
}

export interface PreviewVerification {
  status: string;
  version_no: number;
  checked_by: string;
  checked_at: string;
}

export type LocatorType = 'csv' | 'xlsx' | 'json' | string;

export interface LocatorEnvelope {
  type: LocatorType | null;
  input: Record<string, unknown> | null;
  resolved: Record<string, unknown> | null;
}

export interface DatasetField {
  name: string;
  field_type: string | null;
  description: string | null;
  src_locator: LocatorEnvelope;
  source_file: SourceFileRef;
}

export interface LineageDataset {
  id: string;
  name: string;
  fields: DatasetField[];
}

export interface LineageEdge {
  /** Edge database primary key; the manual edit/delete APIs use it to locate the edge */
  id: number;
  from_dataset: string;
  from_field: string | null;
  to_dataset: string;
  to_field: string | null;
  transform: string | null;
  confidence: number | null;
  source: string;
  note: string | null;
}

export interface LineageGraph {
  datasets: LineageDataset[];
  edges: LineageEdge[];
}

export interface FieldSelection {
  dataset: LineageDataset;
  field: DatasetField;
}

export type PreviewCell = string | number | boolean | null;

export interface CsvPreview {
  header: string[];
  column_index: number;
  rows: PreviewCell[][];
}

export interface XlsxPreview {
  sheet: string;
  header_rows: PreviewCell[][];
  merged_ranges: string[];
  column_index: number;
  row_start: number;
  row_end: number;
  rows: PreviewCell[][];
}

export interface JsonPreview {
  json_path: string;
  hits: number;
  samples: unknown[];
}

export type FieldPreview = CsvPreview | XlsxPreview | JsonPreview;

export interface PreviewResponse {
  file: PreviewFileRef;
  verification: PreviewVerification | null;
  locator: LocatorEnvelope;
  preview: FieldPreview;
}

// ---------- M3: annotations, manual edits, change history and version tags ----------

export type TargetKind = 'dataset' | 'field' | 'edge';
export type ChangeOp = 'added' | 'updated' | 'deleted';

export interface Annotation {
  id: number;
  target_kind: TargetKind;
  target_id: string;
  body: string;
  author: string;
  created_at: string;
}

export interface ChangeEntry {
  id: number;
  op: ChangeOp;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  actor: string;
  created_at: string;
}

export interface VersionTag {
  id: number;
  name: string;
  note: string | null;
  batch_id: number | null;
  change_seq: number;
  created_by: string;
  created_at: string;
}

export interface VersionTagDiffItem {
  entity_kind: TargetKind;
  entity_key: string;
  op: ChangeOp;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface VersionTagDiff {
  summary: { added: number; updated: number; deleted: number };
  items: VersionTagDiffItem[];
}

export interface UserAccount {
  username: string;
  display_name: string | null;
  role: string;
}

export interface ImportBatch {
  id: number;
  version_no: number;
  file_names: string[];
  format: string;
  created_by: string;
  created_at: string;
  rolled_back_at: string | null;
}

/** New-lineage draft produced by the canvas onConnect (either field-level or table-level). */
export interface EdgeDraft {
  from_dataset: string;
  from_field: string | null;
  to_dataset: string;
  to_field: string | null;
}

export interface EdgeCreatePayload extends EdgeDraft {
  transform?: string | null;
  confidence?: number;
  note?: string | null;
}

export interface EdgePatchPayload {
  transform?: string | null;
  note?: string | null;
  confidence?: number;
}

export interface FieldPatchPayload {
  description?: string | null;
  field_type?: string | null;
  src_locator?: Record<string, unknown> | null;
}

export interface AnnotationCreatePayload {
  target_kind: TargetKind;
  target_id: string;
  body: string;
}

// ---------- M4: AI assistant and heuristic lineage suggestions ----------

export interface AiStatus {
  configured: boolean;
  model: string | null;
}

export interface AiChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AiFocus {
  dataset: string;
  field?: string | null;
}

export interface AiToolTrace {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
}

/** Canvas highlight fields declared by mark_highlight (red trace-chain link signal) */
export interface AiHighlightItem {
  dataset: string;
  field: string;
}

/** Candidate edges persisted by suggest_lineage (blue dashed on the canvas, pending manual confirmation) */
export interface AiSuggestionCandidate {
  from_dataset: string;
  from_field: string | null;
  to_dataset: string;
  to_field: string | null;
  confidence: number;
  reason: string;
}

/** Description drafts (generated by draft_descriptions, stored as an annotation after confirmation) */
export interface AiDraftItem {
  id: number;
  dataset: string;
  field: string;
  draft: string;
  model: string;
  status: 'pending' | 'accepted' | 'rejected' | string;
  created_at: string;
  decided_at?: string | null;
}

export interface AiChatResponse {
  answer: string;
  tool_trace: AiToolTrace[];
  /** Subgraph returned by the last trace_lineage tool call, used for canvas linking */
  graph?: LineageGraph;
  /** Highlight fields aggregated from mark_highlight; the frontend applies trace-chain highlighting on the canvas from these */
  highlights?: AiHighlightItem[];
  /** Candidate edges persisted by suggest_lineage (returned on the non-streaming path) */
  suggestions?: AiSuggestionCandidate[];
  /** Description drafts generated by draft_descriptions (returned on the non-streaming path) */
  drafts?: AiDraftItem[];
}

/** SSE streaming chat events (POST /ai/chat/stream, evolution plan 07 §4.3) */
export type AiStreamEvent =
  | { type: 'token'; delta: string }
  | { type: 'tool'; tool: string; args: Record<string, unknown>; ok: boolean }
  | {
      type: 'suggest';
      count: number;
      candidates: AiSuggestionCandidate[];
    }
  | { type: 'drafts'; items: AiDraftItem[] }
  | {
      type: 'done';
      answer: string;
      graph?: LineageGraph;
      highlights?: AiHighlightItem[];
      suggestions?: AiSuggestionCandidate[];
      drafts?: AiDraftItem[];
      tool_trace: AiToolTrace[];
    }
  | { type: 'error'; status: string; detail: string };

export interface AiSuggestion {
  from_dataset: string;
  from_field: string | null;
  to_dataset: string;
  to_field: string | null;
  confidence: number;
  reason: string;
}

export interface AiEdgeKey {
  from_dataset: string;
  from_field: string | null;
  to_dataset: string;
  to_field: string | null;
}
