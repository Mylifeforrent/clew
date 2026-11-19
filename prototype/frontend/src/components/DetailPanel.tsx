import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  AiSuggestion,
  DatasetField,
  FieldSelection,
  LineageEdge,
  LineageGraph,
} from '../types';
import {
  ApiError,
  confirmAiSuggestion,
  patchField,
  rejectAiSuggestion,
  suggestAiEdges,
} from '../lib/api';
import { fieldEntityKey } from '../lib/entities';
import {
  formatConfidence,
  humanizeLocator,
  locatorTypeLabel,
} from '../lib/format';
import { Icon } from './Icon';
import type { IconName } from './Icon';
import { SourceBadge } from './SourceBadge';
import { AnnotationSection } from './AnnotationSection';
import { HistoryDrawer } from './HistoryDrawer';
import type { ToastTone } from './Toast';

interface DetailPanelProps {
  selection: FieldSelection | null;
  graph: LineageGraph | null;
  token: string;
  canEdit: boolean;
  onClose: () => void;
  onPreview: (selection: FieldSelection) => void;
  onRefresh: () => void;
  onNotify: (message: string, tone?: ToastTone) => void;
}

const DETAIL_HINTS: Array<[string, string, IconName]> = [
  ['Locator', 'sheet / rows / columns / JSONPath', 'code'],
  ['Source badge', 'imported · manual · ai', 'link'],
  ['Source preview', 'CSV / XLSX / JSON', 'file-search'],
];

function FileTypeBadge({ type }: { type: string | null | undefined }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-line bg-card px-1.5 py-0.5 font-mono text-[11px] uppercase text-ink-muted">
      <Icon name="file" size={12} />
      {locatorTypeLabel(type)}
    </span>
  );
}

function EmptyDetail() {
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center px-5 py-8">
      <div className="mx-auto w-full max-w-[248px] text-center">
        <div className="relative mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-line bg-page text-blue-600">
          <Icon name="file-search" size={24} />
          <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full border border-line bg-card font-mono text-[11px] text-ink-faint">
            1
          </span>
        </div>
        <h2 className="mt-4 text-xl font-medium text-ink">Verify where a field comes from</h2>
        <p className="mt-2 text-[13px] leading-5 text-ink-muted">
          Click any field in a canvas node to see its properties, a human-readable locator
          and upstream lineage, and open the source file preview directly.
        </p>
      </div>

      <div className="mx-auto mt-7 w-full max-w-[262px] space-y-2">
        {DETAIL_HINTS.map(([title, detail, icon], index) => (
          <div
            key={title}
            className="flex items-center gap-2.5 rounded-lg border border-line-soft bg-card px-3 py-2.5"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-line-soft bg-page text-ink-faint">
              <Icon name={icon} size={13} />
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-ink-soft">{title}</div>
              <div className="mt-0.5 font-mono text-[11px] text-ink-faint">
                {detail}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mx-auto mt-7 flex max-w-[262px] items-start gap-2 rounded-lg border border-dashed border-line px-3 py-2.5 text-[11px] leading-4 text-ink-muted">
        <Icon name="info" size={12} className="mt-0.5 shrink-0" />
        Hover or click a link on the canvas to see its transform description and add annotations in the right-hand panel.
      </div>
    </div>
  );
}

function IncomingEdgeCard({ edge }: { edge: LineageEdge }) {
  return (
    <div className="rounded-xl border border-line-soft bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-mono text-[12px] leading-4 text-ink-soft">
            <span className="text-ink-faint">{edge.from_dataset}.</span>
            <span className="font-medium text-ink">{edge.from_field}</span>
          </div>
          <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-ink-faint">
            <span>Confidence</span>
            <span className="tabular-nums text-ink-soft">
              {formatConfidence(edge.confidence)}
            </span>
            <span className="text-line-strong">·</span>
            <span>Field-level</span>
          </div>
        </div>
        <SourceBadge source={edge.source} withDescription={false} />
      </div>
      <div className="mt-2 border-t border-line-soft pt-2">
        <div className="font-mono text-[11px] leading-4 text-ink-muted">
          <span className="text-ink-faint">Transform · </span>
          {edge.transform || 'Not set'}
        </div>
        {edge.note && (
          <p className="mt-1 text-[11px] leading-4 text-ink-faint">{edge.note}</p>
        )}
      </div>
    </div>
  );
}

interface LocatorDraft {
  column: string;
  header: string;
  sheet: string;
  rowStart: string;
  rowEnd: string;
  headerPath: string;
  headerRows: string;
  jsonPath: string;
}

function textValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function draftFromField(field: DatasetField): LocatorDraft {
  const input = field.src_locator.input ?? {};
  const resolved = field.src_locator.resolved ?? {};
  const type = field.src_locator.type;
  const headerPath = Array.isArray(input.header_path)
    ? input.header_path.map((item) => String(item)).join(' → ')
    : '';
  // CSV header / column and XLSX header_path / column are both either-or semantics:
  // only seed the variant that is actually in effect, so changing the column number does not lose to a header match.
  const csvUsesHeader = type === 'csv' && input.header !== null &&
    input.header !== undefined;
  const xlsxUsesPath = type === 'xlsx' && headerPath.length > 0;

  return {
    column:
      type === 'csv'
        ? csvUsesHeader
          ? ''
          : textValue(input.column ?? resolved.column_index)
        : type === 'xlsx'
          ? xlsxUsesPath
            ? ''
            : textValue(input.column ?? resolved.column)
          : '',
    header: csvUsesHeader ? textValue(input.header) : '',
    sheet: textValue(input.sheet ?? resolved.sheet),
    rowStart: textValue(input.row_start ?? resolved.row_start),
    rowEnd: textValue(input.row_end ?? resolved.row_end),
    headerPath,
    headerRows: textValue(input.header_rows),
    jsonPath: textValue(input.json_path ?? resolved.json_path),
  };
}

function splitHeaderPath(raw: string): string[] {
  return raw
    .split(/[→>,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function suggestionId(item: AiSuggestion): string {
  return `${item.from_dataset}.${item.from_field ?? '*'}->${item.to_dataset}.${item.to_field ?? '*'}`;
}

function suggestionKey(item: AiSuggestion) {
  return {
    from_dataset: item.from_dataset,
    from_field: item.from_field,
    to_dataset: item.to_dataset,
    to_field: item.to_field,
  };
}

function buildLocatorInput(
  type: string | null,
  draft: LocatorDraft,
): Record<string, unknown> {
  if (type === 'csv') {
    const payload: Record<string, unknown> = {};
    if (draft.column.trim()) {
      const column = Number(draft.column);
      if (!Number.isInteger(column) || column < 1) {
        throw new Error('The CSV column number must be an integer greater than or equal to 1.');
      }
      payload.column = column;
    }
    if (draft.header.trim()) payload.header = draft.header.trim();
    if (!payload.column && !payload.header) {
      throw new Error('A CSV locator needs at least a column number or a header name.');
    }
    if (payload.column && payload.header) {
      throw new Error('A CSV locator accepts either a column number or a header name, not both.');
    }
    return payload;
  }

  if (type === 'xlsx') {
    if (!draft.sheet.trim()) {
      throw new Error('An XLSX locator must include a sheet name.');
    }
    const payload: Record<string, unknown> = { sheet: draft.sheet.trim() };
    const headerPath = splitHeaderPath(draft.headerPath);
    if (draft.column.trim() && headerPath.length) {
      throw new Error('An XLSX locator accepts either a column identifier or a header path, not both.');
    }
    if (draft.column.trim()) payload.column = draft.column.trim();
    if (draft.rowStart.trim()) {
      const rowStart = Number(draft.rowStart);
      if (!Number.isInteger(rowStart) || rowStart < 1) {
        throw new Error('The start row must be an integer greater than or equal to 1.');
      }
      payload.row_start = rowStart;
    }
    if (draft.rowEnd.trim()) {
      const rowEnd = Number(draft.rowEnd);
      if (!Number.isInteger(rowEnd) || rowEnd < 1) {
        throw new Error('The end row must be an integer greater than or equal to 1.');
      }
      payload.row_end = rowEnd;
    }
    if (headerPath.length) payload.header_path = headerPath;
    if (draft.headerRows.trim()) {
      const headerRows = Number(draft.headerRows);
      if (!Number.isInteger(headerRows) || headerRows < 1) {
        throw new Error('The header row count must be an integer greater than or equal to 1.');
      }
      payload.header_rows = headerRows;
    }
    return payload;
  }

  if (type === 'json') {
    if (!draft.jsonPath.trim()) {
      throw new Error('A JSON locator must include a JSONPath.');
    }
    return { json_path: draft.jsonPath.trim() };
  }

  throw new Error('The source file type is unknown; the locator cannot be edited.');
}

interface FieldEditorProps {
  token: string;
  datasetId: string;
  field: DatasetField;
  onCancel: () => void;
  onSaved: () => void;
}

function FieldEditor({
  token,
  datasetId,
  field,
  onCancel,
  onSaved,
}: FieldEditorProps) {
  const locatorType = field.src_locator.type;
  const [description, setDescription] = useState(field.description ?? '');
  const [fieldType, setFieldType] = useState(field.field_type ?? '');
  const [draft, setDraft] = useState<LocatorDraft>(() => draftFromField(field));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const initialLocator = (() => {
    try {
      return JSON.stringify(buildLocatorInput(locatorType, draftFromField(field)));
    } catch {
      return '';
    }
  })();

  function updateDraft(patch: Partial<LocatorDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;

    const payload: {
      description: string | null;
      field_type: string | null;
      src_locator?: Record<string, unknown>;
    } = {
      description: description.trim() || null,
      field_type: fieldType.trim() || null,
    };

    if (locatorType) {
      try {
        const nextLocator = buildLocatorInput(locatorType, draft);
        if (JSON.stringify(nextLocator) !== initialLocator) {
          payload.src_locator = nextLocator;
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : 'Invalid locator format.');
        return;
      }
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setSaving(true);
    setError(null);
    try {
      await patchField(token, datasetId, field.name, payload, controller.signal);
      onSaved();
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return;
      setError(
        reason instanceof ApiError
          ? reason.message
          : 'Failed to save the field. Please try again later.',
      );
    } finally {
      if (!controller.signal.aborted) setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-3" noValidate>
      <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2.5">
        <div className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-blue-700">
          <Icon name="edit" size={11} />
          Edit field properties
        </div>
        <p className="mt-1 text-[12px] leading-4 text-blue-800">
          When saving a locator the backend re-runs structural validation and source file verification; on failure it returns 409 and keeps the original value.
        </p>
      </div>

      <div>
        <label htmlFor="field-description" className="mb-1.5 block text-[12px] font-medium text-ink-soft">
          Description
        </label>
        <textarea
          id="field-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="Business meaning of the field (leave empty if not registered)"
          className="field-input resize-y py-2 text-[13px] leading-5"
          disabled={saving}
        />
      </div>

      <div>
        <label htmlFor="field-type" className="mb-1.5 block text-[12px] font-medium text-ink-soft">
          Field type
        </label>
        <input
          id="field-type"
          type="text"
          value={fieldType}
          onChange={(event) => setFieldType(event.target.value)}
          placeholder="e.g. STRING / DECIMAL / TIMESTAMP"
          className="field-input h-8 font-mono text-[13px]"
          disabled={saving}
          maxLength={64}
        />
      </div>

      <div className="rounded-xl border border-line bg-card">
        <div className="flex items-center justify-between border-b border-line-soft px-3 py-2">
          <span className="flex items-center gap-1.5 text-[12px] font-medium text-ink-soft">
            <Icon name="code" size={11} className="text-blue-600" />
            Source locator
          </span>
          <FileTypeBadge type={locatorType} />
        </div>

        <div className="space-y-2.5 px-3 py-2.5">
          {!locatorType && (
            <p className="text-[11px] leading-4 text-ink-muted">
              The source file type is unknown; only the description and field type can be edited.
            </p>
          )}

          {locatorType === 'csv' && (
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">Column number</span>
                <input
                  type="number"
                  min={1}
                  value={draft.column}
                  onChange={(event) =>
                    updateDraft({ column: event.target.value, header: '' })
                  }
                  className="field-input h-8 font-mono text-[13px]"
                  disabled={saving}
                  placeholder="e.g. 3"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">Header name</span>
                <input
                  type="text"
                  value={draft.header}
                  onChange={(event) =>
                    updateDraft({ header: event.target.value, column: '' })
                  }
                  className="field-input h-8 text-[13px]"
                  disabled={saving}
                  placeholder="e.g. order_id"
                />
              </label>
            </div>
          )}
          {locatorType === 'csv' && (
            <p className="text-[11px] leading-4 text-ink-muted">
              Use either a column number or a header name; when a header is given, it is used for locating.
            </p>
          )}

          {locatorType === 'xlsx' && (
            <div className="space-y-2">
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">Sheet</span>
                <input
                  type="text"
                  value={draft.sheet}
                  onChange={(event) => updateDraft({ sheet: event.target.value })}
                  className="field-input h-8 text-[13px]"
                  disabled={saving}
                  placeholder="e.g. Orders"
                />
              </label>
              <div className="grid grid-cols-3 gap-2">
                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">Column</span>
                  <input
                    type="text"
                    value={draft.column}
                    onChange={(event) =>
                      updateDraft({
                        column: event.target.value,
                        headerPath: '',
                        headerRows: '',
                      })
                    }
                    className="field-input h-8 font-mono text-[13px]"
                    disabled={saving}
                    placeholder="e.g. C"
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">Start row</span>
                  <input
                    type="number"
                    min={1}
                    value={draft.rowStart}
                    onChange={(event) => updateDraft({ rowStart: event.target.value })}
                    className="field-input h-8 font-mono text-[13px]"
                    disabled={saving}
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">End row</span>
                  <input
                    type="number"
                    min={1}
                    value={draft.rowEnd}
                    onChange={(event) => updateDraft({ rowEnd: event.target.value })}
                    className="field-input h-8 font-mono text-[13px]"
                    disabled={saving}
                  />
                </label>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">
                  Header path (separated by → or commas)
                </span>
                <input
                  type="text"
                  value={draft.headerPath}
                  onChange={(event) =>
                    updateDraft({
                      headerPath: event.target.value,
                      column: '',
                    })
                  }
                  className="field-input h-8 text-[13px]"
                  disabled={saving}
                  placeholder="e.g. Product info → Order no."
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">Header row count</span>
                <input
                  type="number"
                  min={1}
                  value={draft.headerRows}
                  onChange={(event) => updateDraft({ headerRows: event.target.value })}
                  className="field-input h-8 font-mono text-[13px]"
                  disabled={saving}
                  placeholder="Optional"
                />
              </label>
              <p className="text-[11px] leading-4 text-ink-muted">
                Use either a column identifier or a header path; when a header path is given, it is used for locating.
              </p>
            </div>
          )}

          {locatorType === 'json' && (
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">JSONPath</span>
              <input
                type="text"
                value={draft.jsonPath}
                onChange={(event) => updateDraft({ jsonPath: event.target.value })}
                className="field-input h-8 font-mono text-[13px]"
                disabled={saving}
                placeholder="e.g. $.orders[*].order_id"
              />
            </label>
          )}
        </div>
      </div>

      {error && (
        <div
          className="flex gap-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-[12px] leading-4 text-danger-deep"
          role="alert"
        >
          <Icon name="warning" size={12} className="mt-0.5 shrink-0" />
          <span className="break-words">{error}</span>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={saving}
          className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg bg-blue-600 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 active:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {saving ? (
            <>
              <span className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-white/40 border-t-white" />
              Saving & verifying…
            </>
          ) : (
            <>
              <Icon name="check" size={12} />
              Save
            </>
          )}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="h-8 rounded-lg border border-line-strong bg-card px-3 text-[13px] font-medium text-ink-soft transition-colors duration-150 hover:border-blue-400 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function DetailPanel({
  selection,
  graph,
  token,
  canEdit,
  onClose,
  onPreview,
  onRefresh,
  onNotify,
}: DetailPanelProps) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [editing, setEditing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<AiSuggestion[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestNote, setSuggestNote] = useState<string | null>(null);
  const [busySuggestionKey, setBusySuggestionKey] = useState<string | null>(
    null,
  );
  const suggestAbort = useRef<AbortController | null>(null);

  const datasetId = selection?.dataset.id ?? null;
  const fieldName = selection?.field.name ?? null;

  useEffect(() => {
    setEditing(false);
    setHistoryOpen(false);
    suggestAbort.current?.abort();
    setSuggestions([]);
    setSuggesting(false);
    setSuggestError(null);
    setSuggestNote(null);
    setBusySuggestionKey(null);
  }, [datasetId, fieldName]);

  useEffect(() => () => suggestAbort.current?.abort(), []);

  if (!selection) {
    return (
      <aside className="relative flex w-full shrink-0 flex-col border-t border-line bg-card xl:h-full xl:w-[320px] xl:border-l xl:border-t-0">
        <div className="flex h-12 shrink-0 flex-col justify-center border-b border-line-soft px-4">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
            Inspector
          </div>
          <h2 className="mt-0.5 text-[12px] font-semibold text-ink">Field details</h2>
        </div>
        <EmptyDetail />
      </aside>
    );
  }

  const { dataset, field } = selection;
  const incomingEdges =
    graph?.edges.filter(
      (edge) =>
        edge.to_dataset === dataset.id &&
        edge.to_field === field.name &&
        edge.from_field !== null,
    ) ?? [];
  const locatorText = humanizeLocator(field.src_locator);
  const rawLocator = JSON.stringify(field.src_locator, null, 2);
  // The field itself is imported from a source file; if an upstream field-level edge exists, its source is shown first.
  const fieldSource = incomingEdges[0]?.source ?? 'imported';
  const entityKey = fieldEntityKey(dataset.id, field.name);

  async function copyLocator() {
    const value = `${field.source_file.original_name} · ${locatorText}`;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setCopyError(false);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopyError(true);
      window.setTimeout(() => setCopyError(false), 1800);
    }
  }

  async function handleSuggest() {
    if (suggesting || busySuggestionKey) return;
    suggestAbort.current?.abort();
    const controller = new AbortController();
    suggestAbort.current = controller;
    setSuggesting(true);
    setSuggestError(null);
    setSuggestNote(null);
    try {
      const candidates = await suggestAiEdges(
        token,
        { dataset: dataset.id, field: field.name },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      if (candidates.length > 0) {
        setSuggestions((current) => {
          const merged = new Map(
            current.map((item) => [suggestionId(item), item]),
          );
          for (const item of candidates) {
            merged.set(suggestionId(item), item);
          }
          return Array.from(merged.values());
        });
        onNotify(
          `Generated ${candidates.length} AI candidate lineage edges (source=ai)`,
          'success',
        );
        // New candidates are persisted; refresh the subgraph so ai edges appear on the canvas immediately
        onRefresh();
      } else {
        setSuggestNote(
          suggestions.length > 0
            ? 'No new candidates (existing edges are excluded).'
            : 'No candidates found (existing edges are excluded).',
        );
        onNotify(
          suggestions.length > 0
            ? 'No new candidate lineage'
            : 'No field-level lineage candidates found',
          'info',
        );
      }
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return;
      setSuggestError(
        reason instanceof ApiError
          ? reason.message
          : 'Failed to generate AI suggestions. Please try again later.',
      );
    } finally {
      if (!controller.signal.aborted) setSuggesting(false);
    }
  }

  async function handleConfirmSuggestion(item: AiSuggestion) {
    const key = suggestionId(item);
    if (busySuggestionKey) return;
    suggestAbort.current?.abort();
    const controller = new AbortController();
    suggestAbort.current = controller;
    setBusySuggestionKey(key);
    setSuggestError(null);
    try {
      const edge = await confirmAiSuggestion(
        token,
        suggestionKey(item),
        controller.signal,
      );
      if (controller.signal.aborted) return;
      const remaining = suggestions.filter(
        (candidate) => suggestionId(candidate) !== key,
      );
      setSuggestions(remaining);
      if (remaining.length === 0) setSuggestNote('All candidates have been handled.');
      onNotify(`AI suggestion confirmed: #${edge.id} converted to manual`, 'success');
      onRefresh();
    } catch (reason) {
      if (controller.signal.aborted) return;
      setSuggestError(
        reason instanceof ApiError
          ? reason.message
          : 'Failed to confirm the AI suggestion. Please try again later.',
      );
    } finally {
      if (!controller.signal.aborted) setBusySuggestionKey(null);
    }
  }

  async function handleRejectSuggestion(item: AiSuggestion) {
    const key = suggestionId(item);
    if (busySuggestionKey) return;
    suggestAbort.current?.abort();
    const controller = new AbortController();
    suggestAbort.current = controller;
    setBusySuggestionKey(key);
    setSuggestError(null);
    try {
      await rejectAiSuggestion(token, suggestionKey(item), controller.signal);
      if (controller.signal.aborted) return;
      const remaining = suggestions.filter(
        (candidate) => suggestionId(candidate) !== key,
      );
      setSuggestions(remaining);
      if (remaining.length === 0) setSuggestNote('All candidates have been handled.');
      onNotify('Rejected the AI candidate lineage edge', 'info');
      onRefresh();
    } catch (reason) {
      if (controller.signal.aborted) return;
      setSuggestError(
        reason instanceof ApiError
          ? reason.message
          : 'Failed to reject the AI suggestion. Please try again later.',
      );
    } finally {
      if (!controller.signal.aborted) setBusySuggestionKey(null);
    }
  }

  return (
    <aside
      className="relative flex w-full shrink-0 flex-col border-t border-line bg-card xl:h-full xl:w-[320px] xl:border-l xl:border-t-0"
      aria-label="Field details"
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-line-soft px-4">
        <div className="min-w-0">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
            Field inspection
          </div>
          <div className="mt-1 flex min-w-0 items-center gap-1.5 font-mono text-[12px] text-ink-muted">
            <Icon name="database" size={12} className="shrink-0" />
            <span className="truncate">{dataset.id}</span>
            <Icon name="chevron-right" size={12} className="shrink-0" />
            <span className="truncate text-blue-700">{field.name}</span>
          </div>
        </div>
        <div className="ml-2 flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-transparent text-ink-faint transition-colors duration-150 hover:border-line hover:bg-card hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
            aria-label="View field change history"
            title="Change history"
          >
            <Icon name="history" size={14} />
          </button>
          {canEdit && (
            <button
              type="button"
              onClick={() => setEditing((value) => !value)}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-transparent text-ink-faint transition-colors duration-150 hover:border-line hover:bg-card hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              aria-label={editing ? 'Exit field editing' : 'Edit field properties'}
              title={editing ? 'Exit editing' : 'Edit field'}
            >
              <Icon name="edit" size={14} />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-transparent text-ink-faint transition-colors duration-150 hover:border-line hover:bg-card hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
            aria-label="Close field details"
            title="Close field details"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 pb-7">
        <div className="animate-fade-in">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded border border-line bg-card px-1.5 py-0.5 font-mono text-[11px] uppercase text-ink-muted">
              {field.field_type || 'Type not registered'}
            </span>
            <FileTypeBadge type={field.src_locator.type} />
            <SourceBadge source={fieldSource} />
          </div>
          <h2 className="mt-2.5 break-all font-mono text-lg font-semibold leading-6 text-ink">
            {field.name}
          </h2>
          <p className="mt-1.5 text-[13px] leading-5 text-ink-muted">
            {field.description || 'No field description yet'}
          </p>
        </div>

        {editing ? (
          <FieldEditor
            key={`${dataset.id}.${field.name}`}
            token={token}
            datasetId={dataset.id}
            field={field}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              onNotify('Field properties updated', 'success');
              onRefresh();
            }}
          />
        ) : (
          <>
            <div className="mt-5 rounded-xl border border-line bg-card">
              <div className="flex items-center gap-2 border-b border-line-soft px-3 py-2">
                <Icon name="file" size={12} className="text-blue-600" />
                <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-faint">
                  Source file
                </span>
              </div>
              <div className="px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="min-w-0 truncate font-mono text-[13px] font-medium text-ink"
                    title={field.source_file.original_name}
                  >
                    {field.source_file.original_name}
                  </span>
                  <span className="shrink-0 rounded border border-line bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-muted">
                    Managed file
                  </span>
                </div>
                <div className="mt-1 font-mono text-[11px] text-ink-faint">
                  Source file #{field.source_file.id}
                </div>
              </div>
            </div>

            <section className="mt-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
                  Source file location
                </h3>
                <span className="rounded-full border border-line bg-page px-1.5 py-px font-mono text-[11px] text-ink-faint">
                  Readable locator
                </span>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-3">
                <p className="text-[13px] leading-relaxed text-blue-800">
                  {locatorText}
                </p>
                <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-blue-100 pt-2">
                  <span className="font-mono text-[11px] text-blue-700">
                    Locator envelope · {field.src_locator.type || 'unknown'}
                  </span>
                  <button
                    type="button"
                    onClick={copyLocator}
                    className="flex items-center gap-1 rounded px-1 py-0.5 font-mono text-[11px] text-blue-700 transition-colors duration-150 hover:bg-blue-100/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
                  >
                    <Icon name="copy" size={10} />
                    {copied ? 'Copied' : copyError ? 'Copy failed' : 'Copy locator'}
                  </button>
                </div>
              </div>
            </section>

            <div className="mt-4 flex items-stretch gap-2">
              <button
                type="button"
                onClick={() => onPreview(selection)}
                className="flex h-9 flex-1 items-center justify-center gap-2 rounded-lg bg-blue-600 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 active:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              >
                <Icon name="file-search" size={14} />
                Source preview
              </button>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="flex h-9 items-center justify-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 text-[13px] font-medium text-ink-soft transition-colors duration-150 hover:border-blue-400 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
                >
                  <Icon name="edit" size={14} />
                  Edit
                </button>
              )}
            </div>
            <div className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-ink-faint">
              <Icon name="lock" size={12} />
              {canEdit
                ? 'Source preview is read-only · Editing the field writes to the change log'
                : 'Read-only role · Can view annotations and change history'}
            </div>

            {canEdit && (
              <section className="mt-4">
                <div className="rounded-xl border border-ai/25 bg-ai-soft/40 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ai-deep">
                        <Icon name="sparkles" size={12} className="text-ai" />
                        AI suggestions
                      </div>
                      <p className="mt-1 text-[12px] leading-4 text-ink-muted">
                        Find possibly missing field-level lineage by same-name fields / containment;
                        candidates are stored with source=ai and become manual only after manual confirmation.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleSuggest}
                      disabled={suggesting || busySuggestionKey !== null}
                      className="flex h-8 shrink-0 items-center gap-1 rounded-lg border border-ai/25 bg-card px-2 text-[12px] font-medium text-ai-deep transition-colors duration-150 hover:border-ai/40 hover:bg-ai-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {suggesting ? (
                        <span className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-ai/25 border-t-ai" />
                      ) : (
                        <Icon name="sparkles" size={11} />
                      )}
                      {suggesting ? 'Analyzing…' : 'Suggest'}
                    </button>
                  </div>

                  {suggestError && (
                    <div
                      className="mt-2.5 flex gap-1.5 rounded-lg border border-danger/25 bg-danger-soft px-2.5 py-2 text-[12px] leading-4 text-danger-deep"
                      role="alert"
                    >
                      <Icon name="warning" size={11} className="mt-0.5 shrink-0" />
                      <span className="break-words">{suggestError}</span>
                    </div>
                  )}

                  {suggestions.length > 0 && (
                    <div className="mt-2.5 space-y-2">
                      {suggestions.map((item) => {
                        const key = suggestionId(item);
                        const busy = busySuggestionKey === key;
                        const anyBusy = busySuggestionKey !== null;
                        return (
                          <div
                            key={key}
                            className="rounded-xl border border-ai/20 bg-card p-2.5"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0 space-y-0.5 font-mono text-[12px] leading-4">
                                <div className="break-all">
                                  <span className="text-ink-faint">
                                    {item.from_dataset}.
                                  </span>
                                  <span className="font-medium text-ink-soft">
                                    {item.from_field ?? '*'}
                                  </span>
                                </div>
                                <div className="flex items-start gap-1 text-ink-faint">
                                  <Icon
                                    name="arrow-right"
                                    size={10}
                                    className="mt-0.5 shrink-0"
                                  />
                                  <span className="min-w-0 break-all">
                                    <span>{item.to_dataset}.</span>
                                    <span className="font-medium text-blue-700">
                                      {item.to_field ?? '*'}
                                    </span>
                                  </span>
                                </div>
                              </div>
                              <span className="shrink-0 rounded-full border border-ai/20 bg-ai-soft px-1.5 py-px font-mono text-[11px] text-ai-deep">
                                Conf {formatConfidence(item.confidence)}
                              </span>
                            </div>
                            <p className="mt-1.5 text-[12px] leading-4 text-ink-muted">
                              {item.reason}
                            </p>
                            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-line-soft pt-2">
                              <SourceBadge source="ai" withDescription={false} />
                              <div className="flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => handleConfirmSuggestion(item)}
                                  disabled={anyBusy}
                                  className="flex h-7 items-center gap-1 rounded-lg bg-blue-600 px-2 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 active:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                                >
                                  <Icon name="check" size={12} />
                                  {busy ? 'Confirming…' : 'Confirm'}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleRejectSuggestion(item)}
                                  disabled={anyBusy}
                                  className="flex h-7 items-center gap-1 rounded-lg border border-line-strong bg-card px-2 text-[12px] font-medium text-ink-soft transition-colors duration-150 hover:border-danger/30 hover:text-danger-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  <Icon name="trash" size={12} />
                                  {busy ? 'Rejecting…' : 'Reject'}
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {suggestNote && (
                    <div className="mt-2.5 rounded-lg border border-dashed border-line bg-page px-2.5 py-2 text-center text-[12px] text-ink-muted">
                      {suggestNote}
                    </div>
                  )}
                </div>
              </section>
            )}

            <section className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
                  Upstream lineage
                </h3>
                <span className="font-mono text-[11px] tabular-nums text-ink-faint">
                  {incomingEdges.length} field-level edges
                </span>
              </div>
              {incomingEdges.length > 0 ? (
                <div className="space-y-2">
                  {incomingEdges.map((edge, index) => (
                    <IncomingEdgeCard
                      key={`${edge.from_dataset}-${edge.from_field}-${index}`}
                      edge={edge}
                    />
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-line px-3 py-3 text-center">
                  <div className="font-mono text-[12px] text-ink-muted">
                    Root field / No field-level incoming edges
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-ink-muted">
                    This field may be the start of a chain or covered only by table-level lineage.
                  </p>
                </div>
              )}
            </section>

            <AnnotationSection
              token={token}
              targetKind="field"
              targetId={entityKey}
              canWrite={canEdit}
            />

            <section className="mt-5">
              <button
                type="button"
                onClick={() => setHistoryOpen(true)}
                className="flex w-full items-center justify-between rounded-xl border border-line bg-card px-3 py-2.5 text-[13px] font-medium text-ink-muted transition-colors duration-150 hover:border-blue-400 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              >
                <span className="flex items-center gap-1.5">
                  <Icon name="history" size={12} />
                  Change history
                </span>
                <Icon name="chevron-right" size={12} className="text-ink-faint" />
              </button>
            </section>

            <details className="group mt-4 rounded-xl border border-line-soft bg-card">
              <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-[13px] font-medium text-ink-muted outline-none transition-colors duration-150 hover:text-ink focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white">
                View raw locator
                <Icon
                  name="chevron-down"
                  size={12}
                  className="text-ink-faint transition-transform duration-150 group-open:rotate-180"
                />
              </summary>
              <pre className="max-h-52 overflow-auto border-t border-line-soft bg-subtle/50 px-3 py-2.5 font-mono text-[11px] leading-4 text-ink-muted">
                {rawLocator}
              </pre>
            </details>
          </>
        )}
      </div>

      {historyOpen && (
        <HistoryDrawer
          token={token}
          entityKind="field"
          entityKey={entityKey}
          title={entityKey}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </aside>
  );
}
