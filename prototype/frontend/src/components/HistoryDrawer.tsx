import { useEffect, useRef, useState } from 'react';
import type { ChangeEntry, ChangeOp, LocatorEnvelope, TargetKind } from '../types';
import { ApiError, getChanges, isAbortError } from '../lib/api';
import { formatDateTime, humanizeLocator } from '../lib/format';
import { Icon } from './Icon';

interface HistoryDrawerProps {
  token: string;
  entityKind: TargetKind;
  entityKey: string;
  title: string;
  onClose: () => void;
}

const FIELD_LABELS: Record<string, string> = {
  dataset_id: 'Dataset',
  name: 'Name',
  field_type: 'Type',
  source_file_id: 'Source file',
  src_locator: 'Locator',
  description: 'Description',
  from_dataset: 'Upstream dataset',
  from_field: 'Upstream field',
  to_dataset: 'Downstream dataset',
  to_field: 'Downstream field',
  transform: 'Transform',
  confidence: 'Confidence',
  source: 'Source',
  note: 'Note',
};

const KIND_LABELS: Record<TargetKind, string> = {
  dataset: 'Dataset',
  field: 'Field',
  edge: 'Lineage edge',
};

const OP_LABELS: Record<ChangeOp, string> = {
  added: 'Added',
  updated: 'Updated',
  deleted: 'Deleted',
};

const OP_STYLES: Record<ChangeOp, string> = {
  added: 'border-transparent bg-success-soft text-success-deep',
  updated: 'border-transparent bg-warning-soft text-warning-deep',
  deleted: 'border-transparent bg-danger-soft text-danger-deep',
};

const OP_DOT_STYLES: Record<ChangeOp, string> = {
  added: 'bg-success',
  updated: 'bg-warning',
  deleted: 'bg-danger',
};

function valueText(value: unknown): string {
  if (value === null || value === undefined) return 'Empty';
  if (typeof value === 'string') return value || 'Empty';
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if ('type' in record && ('input' in record || 'resolved' in record)) {
      return humanizeLocator(value as LocatorEnvelope);
    }
    try {
      return JSON.stringify(value);
    } catch {
      return '[Cannot display]';
    }
  }
  return String(value);
}

function changedKeys(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
): string[] {
  const keys = new Set([
    ...Object.keys(before ?? {}),
    ...Object.keys(after ?? {}),
  ]);
  return Array.from(keys).filter(
    (key) =>
      JSON.stringify(before?.[key] ?? null) !==
      JSON.stringify(after?.[key] ?? null),
  );
}

function ChangeSummary({ entry }: { entry: ChangeEntry }) {
  const keys = changedKeys(entry.before, entry.after);
  if (entry.op === 'updated') {
    if (keys.length === 0) {
      return (
        <p className="text-[11px] leading-4 text-ink-faint">
          Identical to the previous version (no substantive change).
        </p>
      );
    }
    return (
      <ul className="space-y-1">
        {keys.map((key) => (
          <li
            key={key}
            className="grid grid-cols-[64px_minmax(0,1fr)] gap-x-1.5 gap-y-1 text-[11px] leading-4"
          >
            <span className="text-ink-faint">{FIELD_LABELS[key] ?? key}</span>
            <span className="min-w-0 break-words font-mono text-[11px] leading-4">
              <span className="line-through decoration-line-strong text-ink-faint">
                {valueText(entry.before?.[key])}
              </span>
              <span className="mx-1 text-ink-faint">→</span>
              <span className="text-blue-800">{valueText(entry.after?.[key])}</span>
            </span>
          </li>
        ))}
      </ul>
    );
  }

  const snapshot = entry.op === 'deleted' ? entry.before : entry.after;
  const summaryKeys = keys.slice(0, 5);
  if (!snapshot || summaryKeys.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {summaryKeys.map((key) => (
        <span key={key} className="min-w-0 break-words font-mono text-[11px] leading-4 text-ink-muted">
          <span className="text-ink-faint">{FIELD_LABELS[key] ?? key} </span>
          {valueText(snapshot[key])}
        </span>
      ))}
    </div>
  );
}

/** Change history drawer for fields / edges; data comes from GET /changes, ordered by id descending. */
export function HistoryDrawer({
  token,
  entityKind,
  entityKey,
  title,
  onClose,
}: HistoryDrawerProps) {
  const [entries, setEntries] = useState<ChangeEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getChanges(token, entityKind, entityKey, 50, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) setEntries(rows);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || isAbortError(reason)) return;
        setError(
          reason instanceof ApiError
            ? reason.message
            : 'Unable to load the change history. Please try again later.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, entityKind, entityKey, reloadKey]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-slate-900/25 animate-fade-in"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="relative z-[41] flex h-full w-full flex-col overflow-hidden border-l border-line bg-card shadow-float animate-drawer-in sm:w-[360px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-drawer-title"
      >
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line-soft px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-700">
              <Icon name="history" size={16} />
            </span>
            <div className="min-w-0">
              <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
                Change history · {KIND_LABELS[entityKind]}
              </div>
              <h2
                id="history-drawer-title"
                className="mt-0.5 truncate font-mono text-[13px] font-semibold text-ink"
              >
                {title}
              </h2>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => setReloadKey((value) => value + 1)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              aria-label="Refresh change history"
              title="Refresh"
            >
              <Icon name="refresh" size={14} />
            </button>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              aria-label="Close change history"
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4">
          <div className="mb-3 rounded-lg border border-line bg-card px-3 py-2.5">
            <p className="break-all font-mono text-[12px] leading-4 text-ink-soft">
              {entityKey}
            </p>
            <p className="mt-1.5 flex items-start gap-1.5 text-[11px] leading-4 text-ink-muted">
              <Icon name="info" size={11} className="mt-0.5 shrink-0 text-ink-faint" />
              <span>
                The change log is shown newest first (up to 50 entries). Imports and manual edits are recorded,
                annotations are not written to the change log.
              </span>
            </p>
          </div>

          {loading && (
            <div className="space-y-2" aria-hidden="true">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-[86px] animate-soft-pulse rounded-xl border border-line bg-subtle"
                />
              ))}
            </div>
          )}

          {!loading && error && (
            <div className="rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3" role="alert">
              <p className="text-[13px] leading-5 text-danger-deep">{error}</p>
              <button
                type="button"
                onClick={() => setReloadKey((value) => value + 1)}
                className="mt-2 inline-flex h-7 items-center gap-1 rounded-lg border border-line-strong bg-card px-2 text-[11px] font-medium text-ink-soft transition-colors duration-150 hover:border-blue-400 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              >
                <Icon name="refresh" size={11} />
                Reload
              </button>
            </div>
          )}

          {!loading && !error && entries?.length === 0 && (
            <div className="rounded-xl border border-dashed border-line px-4 py-8 text-center">
              <div className="text-[12px] text-ink-muted">No change records yet</div>
              <p className="mt-1 text-[11px] text-ink-muted">
                Creates and updates of this entity have not been written to the change log yet.
              </p>
            </div>
          )}

          {!loading && !error && Boolean(entries?.length) && (
            <ol className="relative space-y-2.5 border-l border-line-soft pl-4">
              {(entries ?? []).map((entry) => (
                <li key={entry.id} className="relative">
                  <span
                    className={`absolute -left-[21px] top-3 h-2 w-2 rounded-full ring-2 ring-card ${OP_DOT_STYLES[entry.op]}`}
                    aria-hidden="true"
                  />
                  <article className="rounded-xl border border-line-soft bg-card px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span
                        className={`rounded border px-1.5 py-px font-mono text-[11px] ${OP_STYLES[entry.op]}`}
                      >
                        {OP_LABELS[entry.op]}
                      </span>
                      <span className="font-mono text-[11px] tabular-nums text-ink-faint">
                        #{entry.id}
                      </span>
                      <span className="ml-auto font-mono text-[11px] text-ink-faint">
                        {formatDateTime(entry.created_at)}
                      </span>
                    </div>
                    <div className="mt-1.5">
                      <ChangeSummary entry={entry} />
                    </div>
                    <div className="mt-1.5 flex items-center gap-1 font-mono text-[11px] text-ink-faint">
                      <Icon name="user" size={10} />
                      Actor {entry.actor}
                    </div>
                  </article>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </div>
  );
}
