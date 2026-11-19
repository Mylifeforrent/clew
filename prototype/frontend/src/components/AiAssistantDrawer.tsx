import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import type {
  AiChatMessage,
  AiDraftItem,
  AiFocus,
  AiHighlightItem,
  AiStatus,
  AiToolTrace,
  LineageGraph,
} from '../types';
import {
  acceptDescriptionDraft,
  ApiError,
  getAiStatus,
  isAbortError,
  rejectDescriptionDraft,
  sendAiChatStream,
} from '../lib/api';
import { Icon } from './Icon';

interface AiAssistantDrawerProps {
  open: boolean;
  token: string;
  /** Dataset/field currently focused on the canvas, used as the focus context for each chat round */
  focus: AiFocus | null;
  /** Only editor+ sees the accept/reject buttons for description drafts */
  canEdit: boolean;
  onClose: () => void;
  /**
   * Response linking: when a graph is present, hand the subgraph to Workspace to render
   * with the existing canvas state; highlights (mark_highlight declarations) are also
   * handed to Workspace to drive canvas trace highlighting.
   */
  onGraph: (graph: LineageGraph | null, highlights?: AiHighlightItem[]) => void;
  /** Workspace refreshes the canvas (blue dashed candidate edges) after suggest_lineage persists candidates */
  onSuggested: (count: number) => void;
  /** Clicking an evidence anchor in an answer: apply that field as the canvas trace focus */
  onFieldFocus: (dataset: string, field: string) => void;
}

interface ChatEntry {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  toolTrace?: AiToolTrace[];
  graph?: LineageGraph;
  drafts?: AiDraftItem[];
  /** SSE streaming in progress: show the blinking cursor and in-progress tool state */
  streaming?: boolean;
  error?: boolean;
}

const TOOL_LABELS: Record<string, string> = {
  search_fields: 'Search fields',
  get_field_details: 'Field details',
  trace_lineage: 'Trace lineage',
  get_field_history: 'Change history',
  mark_highlight: 'Mark highlight',
  suggest_lineage: 'Suggest lineage',
  analyze_impact: 'Impact analysis',
  draft_descriptions: 'Draft descriptions',
};

const EXAMPLE_PROMPTS = [
  'Where does order_no in the orders table come from?',
  'Where is the source file locator for this field?',
  'Which fields were changed recently?',
];

const NOT_CONFIGURED_TEXT =
  'LLM is not configured. Set LLM_* in .env (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL).';

function focusLabel(focus: AiFocus | null): string {
  if (!focus) return 'No dataset focused';
  return focus.field ? `${focus.dataset}.${focus.field}` : focus.dataset;
}

/** Common file extensions are not treated as field references (so d0_orders.csv is not read as dataset.field) */
const NON_FIELD_TOKENS = new Set([
  'csv', 'xlsx', 'xls', 'json', 'md', 'txt', 'png', 'svg', 'db', 'py', 'ts',
]);

const FIELD_REF_PATTERN = /\b([a-zA-Z][\w-]{0,31})\.([a-zA-Z][\w-]{0,63})\b/g;

/**
 * GFM markdown rendering (evolution plan 07: the common industry chat-UI approach —
 * tables/code blocks/lists rendered with styles rather than raw text). Security:
 * react-markdown does not execute inline HTML by default.
 */
function linkifyFieldRefs(markdown: string): string {
  /** Replace `dataset.field` text in non-code segments with anchor links, taken over by the a component as chips. */
  const segments = markdown.split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g);
  return segments
    .map((segment, index) => {
      if (index % 2 === 1) return segment; // Keep code segments as-is
      return segment.replace(
        FIELD_REF_PATTERN,
        (full, dataset: string, field: string) => {
          if (NON_FIELD_TOKENS.has(field.toLowerCase())) return full;
          return `[${full}](#ref:${encodeURIComponent(dataset)}.${encodeURIComponent(field)})`;
        },
      );
    })
    .join('');
}

function FieldRefChip({
  dataset,
  field,
  label,
  onFieldFocus,
}: {
  dataset: string;
  field: string;
  label: string;
  onFieldFocus: (dataset: string, field: string) => void;
}) {
  return (
    <button
      type="button"
      title={`Trace ${dataset}.${field} on the canvas`}
      onClick={() => onFieldFocus(dataset, field)}
      className="mx-0.5 inline-flex items-center rounded border border-ai/25 bg-ai-soft px-1 py-px align-baseline font-mono text-[11px] leading-4 text-ai-deep transition-colors duration-150 hover:border-ai/50 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
    >
      {label}
    </button>
  );
}

function AnswerText({
  content,
  onFieldFocus,
  streaming = false,
}: {
  content: string;
  onFieldFocus: (dataset: string, field: string) => void;
  streaming?: boolean;
}) {
  const components = useMemo<Components>(() => ({
    a: ({ href, children }) => {
      if (href?.startsWith('#ref:')) {
        try {
          const raw = decodeURIComponent(href.slice(5));
          const dot = raw.indexOf('.');
          if (dot > 0) {
            return (
              <FieldRefChip
                dataset={raw.slice(0, dot)}
                field={raw.slice(dot + 1)}
                label={String(children ?? raw)}
                onFieldFocus={onFieldFocus}
              />
            );
          }
        } catch {
          // Treat it as a normal link when decoding fails
        }
      }
      return (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-800"
        >
          {children}
        </a>
      );
    },
    code: ({ className, children }) => {
      const text = String(children ?? '').replace(/\n$/, '');
      const isBlock = (className ?? '').includes('language-') || text.includes('\n');
      if (isBlock) {
        return (
          <pre className="my-2 overflow-x-auto rounded-lg border border-line bg-page px-2.5 py-2 font-mono text-[11px] leading-5 text-ink-soft">
            <code>{text}</code>
          </pre>
        );
      }
      const match = /^([a-zA-Z][\w-]{0,31})\.([a-zA-Z][\w-]{0,63})$/.exec(text);
      if (match && !NON_FIELD_TOKENS.has(match[2].toLowerCase())) {
        return (
          <FieldRefChip
            dataset={match[1]}
            field={match[2]}
            label={text}
            onFieldFocus={onFieldFocus}
          />
        );
      }
      return (
        <code className="rounded bg-subtle px-1 py-px font-mono text-[11px] text-ink-soft">
          {text}
        </code>
      );
    },
    pre: ({ children }) => <>{children}</>,
    table: ({ children }) => (
      <div className="my-2 overflow-x-auto rounded-lg border border-line">
        <table className="w-full border-collapse text-[11px]">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-subtle">{children}</thead>,
    th: ({ children }) => (
      <th className="whitespace-nowrap border-b border-line px-2 py-1.5 text-left font-medium text-ink-soft">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-t border-line-soft px-2 py-1.5 align-top text-ink-soft">
        {children}
      </td>
    ),
    p: ({ children }) => (
      <p className="my-1.5 break-words text-[13px] leading-6 text-ink-soft first:mt-0 last:mb-0">
        {children}
      </p>
    ),
    ul: ({ children }) => (
      <ul className="my-1.5 list-disc space-y-0.5 pl-4 text-[13px] leading-6 text-ink-soft">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="my-1.5 list-decimal space-y-0.5 pl-4 text-[13px] leading-6 text-ink-soft">
        {children}
      </ol>
    ),
    li: ({ children }) => <li className="break-words">{children}</li>,
    h1: ({ children }) => (
      <h1 className="mb-1 mt-3 text-[15px] font-semibold text-ink first:mt-0">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="mb-1 mt-3 text-[14px] font-semibold text-ink first:mt-0">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-1 mt-2.5 text-[13px] font-semibold text-ink first:mt-0">{children}</h3>
    ),
    h4: ({ children }) => (
      <h4 className="mb-1 mt-2 text-[13px] font-semibold text-ink first:mt-0">{children}</h4>
    ),
    strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-2 border-line-strong pl-2 text-[12px] leading-5 text-ink-muted">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-2.5 border-line-soft" />,
  }), [onFieldFocus]);

  return (
    <div className="break-words text-[13px] leading-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={components}
      >
        {linkifyFieldRefs(content)}
      </ReactMarkdown>
      {streaming && (
        <span
          className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse bg-ai align-middle"
          aria-hidden="true"
        />
      )}
    </div>
  );
}

/** Description draft confirmation card: accept → write an annotation; reject → do not generate it again. */
function DraftCard({
  item,
  token,
  canEdit,
  onUpdate,
}: {
  item: AiDraftItem;
  token: string;
  canEdit: boolean;
  onUpdate: (next: AiDraftItem) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function decide(accept: boolean) {
    setBusy(true);
    try {
      if (accept) {
        onUpdate(await acceptDescriptionDraft(token, item.id));
      } else {
        await rejectDescriptionDraft(token, item.id);
        onUpdate({
          ...item,
          status: 'rejected',
          decided_at: new Date().toISOString(),
        });
      }
    } catch {
      // Stay pending on failure so the card can be retried
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 rounded-lg border border-ai/25 bg-ai-soft/60 px-2.5 py-2">
      <div className="flex items-center gap-1.5">
        <Icon name="sparkles" size={11} className="shrink-0 text-ai" />
        <span className="font-mono text-[11px] font-medium text-ai-deep">
          {item.dataset}.{item.field}
        </span>
        <span className="shrink-0 font-mono text-[11px] text-ink-faint">
          Description draft
        </span>
        {item.status === 'accepted' && (
          <span className="ml-auto shrink-0 rounded bg-success-soft px-1.5 py-px font-mono text-[11px] text-success-deep">
            Accepted · Written as annotation
          </span>
        )}
        {item.status === 'rejected' && (
          <span className="ml-auto shrink-0 rounded bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-faint">
            Rejected
          </span>
        )}
      </div>
      <p className="mt-1.5 text-[12px] leading-5 text-ink">{item.draft}</p>
      {item.status === 'pending' && canEdit && (
        <div className="mt-2 flex items-center gap-1.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => decide(true)}
            className="inline-flex h-7 items-center rounded-md bg-blue-600 px-2.5 text-[12px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:opacity-50"
          >
            Accept (write annotation)
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide(false)}
            className="inline-flex h-7 items-center rounded-md border border-line-strong bg-card px-2.5 text-[12px] font-medium text-ink-soft transition-colors duration-150 hover:border-blue-400 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:opacity-50"
          >
            Reject
          </button>
          {busy && (
            <span className="text-[11px] text-ink-faint">Processing…</span>
          )}
        </div>
      )}
      {item.status === 'pending' && !canEdit && (
        <p className="mt-1.5 text-[11px] text-ink-faint">
          Only editor and above can accept/reject drafts.
        </p>
      )}
    </div>
  );
}

function ToolTraceCard({ trace }: { trace: AiToolTrace[] }) {
  // Pure UI collapse state: collapsed by default; messages with failed calls start expanded
  const [open, setOpen] = useState(() => trace.some((item) => !item.ok));
  if (trace.length === 0) return null;
  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-line bg-page">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left transition-colors duration-150 hover:bg-subtle/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
      >
        <Icon name="code" size={12} className="shrink-0 text-ink-faint" />
        <span className="shrink-0 text-[11px] font-medium text-ink-muted">
          Tool calls · {trace.length}
        </span>
        <span className="flex min-w-0 flex-1 flex-wrap gap-1">
          {trace.map((item, index) => (
            <span
              key={`${item.tool}-${index}`}
              className="inline-flex max-w-full items-center gap-1 rounded border border-line bg-card px-1.5 py-px font-mono text-[11px] text-ink-muted"
              title={`${TOOL_LABELS[item.tool] ?? 'Tool call'} ${JSON.stringify(item.args)}`}
            >
              <span className="shrink-0">{TOOL_LABELS[item.tool] ?? 'Tool call'}</span>
              <span
                className={`shrink-0 font-semibold ${
                  item.ok ? 'text-success' : 'text-danger'
                }`}
                aria-label={item.ok ? 'Call succeeded' : 'Call failed'}
              >
                {item.ok ? '✓' : '✗'}
              </span>
            </span>
          ))}
        </span>
        <Icon
          name="chevron-down"
          size={12}
          className={`shrink-0 text-ink-faint transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-line-soft px-2.5 py-1.5">
          {trace.map((item, index) => (
            <div
              key={`${item.tool}-detail-${index}`}
              className={`flex items-start gap-2 rounded-md px-1 py-1.5 ${
                item.ok ? '' : 'bg-danger-soft'
              }`}
            >
              <Icon
                name={item.ok ? 'check' : 'close'}
                size={12}
                className={`mt-0.5 shrink-0 ${item.ok ? 'text-success' : 'text-danger'}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={`text-[12px] font-medium ${
                      item.ok ? 'text-ink-soft' : 'text-danger-deep'
                    }`}
                  >
                    {TOOL_LABELS[item.tool] ?? 'Tool call'}
                  </span>
                  <span className="rounded bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-muted">
                    {item.tool}
                  </span>
                </div>
                <p className="mt-1 whitespace-pre-wrap break-all rounded-md bg-subtle px-2 py-1.5 font-mono text-[11px] leading-4 text-ink-muted">
                  {JSON.stringify(item.args)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AiAssistantDrawer({
  open,
  token,
  focus,
  canEdit,
  onClose,
  onGraph,
  onSuggested,
  onFieldFocus,
}: AiAssistantDrawerProps) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusReloadKey, setStatusReloadKey] = useState(0);

  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const entrySeq = useRef(1);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const configured = status?.configured === true;

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setStatusLoading(true);
    setStatusError(null);
    getAiStatus(token, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setStatus(result);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || isAbortError(reason)) return;
        // Treat a status endpoint failure conservatively as unavailable; show a retry entry in the input area instead of crashing.
        setStatus(null);
        setStatusError(
          reason instanceof ApiError
            ? reason.message
            : 'Unable to read the AI status. Please try again later.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatusLoading(false);
      });
    return () => controller.abort();
  }, [open, token, statusReloadKey]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    inputRef.current?.focus();

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
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const node = listRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [entries, sending, open]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const updateEntry = useCallback(
    (id: number, patch: (entry: ChatEntry) => ChatEntry) => {
      setEntries((current) =>
        current.map((entry) => (entry.id === id ? patch(entry) : entry)),
      );
    },
    [],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || sending || !configured) return;

    const userEntry: ChatEntry = {
      id: entrySeq.current,
      role: 'user',
      content: text,
    };
    entrySeq.current += 1;
    const assistantId = entrySeq.current;
    entrySeq.current += 1;
    setEntries((current) => [
      ...current,
      userEntry,
      { id: assistantId, role: 'assistant', content: '', streaming: true },
    ]);
    setInput('');
    setSending(true);

    // Send back only user/assistant text with content; system prompts are fixed by the backend.
    const history: AiChatMessage[] = [
      ...entries,
      userEntry,
    ]
      .filter((entry) => !entry.error && entry.content.trim().length > 0)
      .map((entry) => ({
        role: entry.role,
        content: entry.content.slice(0, 8000),
      }))
      .slice(-50);
    const focusPayload: AiFocus | undefined = focus?.dataset.trim()
      ? {
          dataset: focus.dataset,
          ...(focus.field?.trim() ? { field: focus.field } : {}),
        }
      : undefined;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await sendAiChatStream(
        token,
        { messages: history, ...(focusPayload ? { focus: focusPayload } : {}) },
        (event) => {
          switch (event.type) {
            case 'token':
              updateEntry(assistantId, (entry) => ({
                ...entry,
                content: entry.content + event.delta,
              }));
              break;
            case 'tool':
              updateEntry(assistantId, (entry) => ({
                ...entry,
                toolTrace: [
                  ...(entry.toolTrace ?? []),
                  { tool: event.tool, args: event.args, ok: event.ok },
                ],
              }));
              break;
            case 'suggest':
              onSuggested(event.count);
              break;
            case 'drafts':
              updateEntry(assistantId, (entry) => ({
                ...entry,
                drafts: event.items,
              }));
              break;
            case 'done':
              updateEntry(assistantId, (entry) => ({
                ...entry,
                content: event.answer,
                toolTrace: event.tool_trace,
                graph: event.graph,
                drafts:
                  event.drafts && event.drafts.length > 0
                    ? event.drafts
                    : entry.drafts,
                streaming: false,
              }));
              // Notify Workspace on every answer round: without a graph only the highlight focus
              // is updated (no declared highlights means explicitly clearing the previous trace state)
              onGraph(event.graph ?? null, event.highlights);
              break;
            case 'error':
              updateEntry(assistantId, (entry) => ({
                ...entry,
                streaming: false,
                error: true,
                content: `AI service returned ${event.status}: ${event.detail}`,
              }));
              break;
          }
        },
        controller.signal,
      );
      updateEntry(assistantId, (entry) => ({
        ...entry,
        streaming: false,
      }));
    } catch (reason) {
      if (isAbortError(reason)) {
        updateEntry(assistantId, (entry) => ({
          ...entry,
          streaming: false,
          content: entry.content || '(Cancelled)',
        }));
      } else {
        updateEntry(assistantId, (entry) => ({
          ...entry,
          streaming: false,
          error: true,
          content:
            reason instanceof ApiError
              ? reason.message
              : 'Cannot reach the AI service. Please try again later.',
        }));
      }
    } finally {
      if (!controller.signal.aborted) setSending(false);
    }
  }

  if (!open) return null;

  const inputDisabled = !configured || sending || statusLoading;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-slate-900/25 animate-fade-in"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="relative z-[41] flex h-full w-full flex-col overflow-hidden border-l border-line bg-card shadow-float animate-drawer-in sm:w-[480px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-drawer-title"
      >
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line-soft px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-ai/25 bg-ai-soft text-ai">
              <Icon name="sparkles" size={16} />
            </span>
            <h2
              id="ai-drawer-title"
              className="min-w-0 text-[14px] font-semibold text-ink"
            >
              AI assistant
            </h2>
            {statusLoading ? (
              <span
                className="h-3 w-3 shrink-0 animate-spin rounded-full border-[1.5px] border-ai/25 border-t-ai"
                aria-label="Loading AI status"
              />
            ) : configured && status?.model ? (
              <span
                className="max-w-[180px] truncate rounded-full border border-ai/25 bg-ai-soft px-2 py-px font-mono text-[11px] text-ai-deep"
                title={status.model}
              >
                {status.model}
              </span>
            ) : (
              <span className="shrink-0 rounded-full border border-line bg-subtle px-2 py-px font-mono text-[11px] text-ink-muted">
                {statusError ? 'Unknown status' : 'Not configured'}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => setStatusReloadKey((value) => value + 1)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              aria-label="Recheck LLM configuration"
              title="Recheck configuration"
            >
              <Icon name="refresh" size={14} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
              aria-label="Close the AI assistant"
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        </header>

        <div className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-line-soft bg-page px-4">
          <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
            Current focus
          </span>
          <span
            className={`min-w-0 truncate font-mono text-[12px] ${
              focus ? 'font-medium text-blue-700' : 'text-ink-faint'
            }`}
            title={focusLabel(focus)}
          >
            {focusLabel(focus)}
          </span>
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-card px-1.5 py-px font-mono text-[11px] text-ink-muted">
            <Icon name="lock" size={10} />
            Read-only tools
          </span>
        </div>

        {(statusError || (!statusLoading && status && !status.configured)) && (
          <div className="shrink-0 border-b border-line-soft px-4 py-2.5">
            <div
              className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-[12px] leading-5 ${
                statusError
                  ? 'border-danger/25 bg-danger-soft text-danger-deep'
                  : 'border-warning/25 bg-warning-soft text-warning-deep'
              } animate-fade-in`}
              role="status"
            >
              <Icon
                name="warning"
                size={12}
                className={`mt-0.5 shrink-0 ${statusError ? 'text-danger' : 'text-warning'}`}
              />
              <div className="min-w-0">
                <div className="font-medium">
                  {statusError ? 'Unable to read AI status' : 'AI assistant unavailable'}
                </div>
                <p className="mt-0.5 break-words">
                  {statusError ?? NOT_CONFIGURED_TEXT}
                </p>
                {!statusError && (
                  <p className="mt-0.5 break-words">
                    After configuring, click refresh in the top-right corner to re-check.
                  </p>
                )}
                {statusError && (
                  <button
                    type="button"
                    onClick={() => setStatusReloadKey((value) => value + 1)}
                    className="mt-1.5 inline-flex h-7 items-center gap-1 rounded-md border border-danger/25 bg-card px-2 font-mono text-[11px] text-danger-deep transition-colors duration-150 hover:border-danger/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
                  >
                    <Icon name="refresh" size={11} />
                    Retry
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <div
          ref={listRef}
          className="min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4 pb-6"
          role="log"
          aria-live="polite"
          aria-label="AI chat messages"
        >
          {entries.length === 0 && !sending ? (
            <div className="flex min-h-full flex-col items-center justify-center px-3 py-8 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-ai/25 bg-ai-soft text-ai">
                <Icon name="sparkles" size={24} />
              </div>
              <h3 className="mt-4 text-xl font-medium text-ink">
                Query lineage in natural language
              </h3>
              <p className="mt-2 max-w-[300px] text-[13px] leading-6 text-ink-muted">
                The AI calls tools to query fields, upstream/downstream subgraphs and change history.
                Field references in answers can be clicked to trace on the canvas; it can also suggest
                lineage edges and draft field descriptions (effective only after confirmation).
              </p>
              <div className="mt-5 grid w-full max-w-[300px] gap-1.5">
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => {
                      setInput(prompt);
                      inputRef.current?.focus();
                    }}
                    disabled={inputDisabled}
                    className="w-full rounded-lg border border-line bg-card px-3 py-2 text-left text-[12px] text-ink-muted transition-colors duration-150 hover:border-blue-300 hover:bg-blue-50/60 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {entries.map((entry) =>
                entry.role === 'user' ? (
                  <div key={entry.id} className="flex flex-col items-end">
                    <div className="mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint">
                      You
                    </div>
                    <div className="max-w-[88%] whitespace-pre-wrap break-words rounded-xl rounded-tr-md border border-blue-100 bg-blue-50 px-3 py-2 text-[13px] leading-5 text-ink">
                      {entry.content}
                    </div>
                  </div>
                ) : (
                  <div key={entry.id}>
                    <div className="mb-1 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint">
                      <Icon name="sparkles" size={10} className="text-ai" />
                      AI assistant
                    </div>
                    <div
                      className={`rounded-xl rounded-tl-md border px-3 py-2.5 ${
                        entry.error
                          ? 'border-danger/25 bg-danger-soft/70'
                          : 'border-line bg-card'
                      }`}
                    >
                      {entry.toolTrace && entry.toolTrace.length > 0 && (
                        <ToolTraceCard trace={entry.toolTrace} />
                      )}
                      {entry.content.trim() ? (
                        <AnswerText
                          content={entry.content}
                          onFieldFocus={onFieldFocus}
                          streaming={entry.streaming}
                        />
                      ) : entry.streaming ? (
                        <p className="flex items-center gap-2 text-[12px] text-ink-muted">
                          <span
                            className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-ai/25 border-t-ai"
                            aria-hidden="true"
                          />
                          Calling tools and composing the answer…
                        </p>
                      ) : (
                        <p className="text-[12px] italic leading-5 text-ink-faint">
                          The model returned no text answer.
                        </p>
                      )}
                      {(entry.drafts ?? []).length > 0 && (
                        <div className="mt-2 space-y-2">
                          {(entry.drafts ?? []).map((draft) => (
                            <DraftCard
                              key={draft.id}
                              item={draft}
                              token={token}
                              canEdit={canEdit}
                              onUpdate={(next) =>
                                updateEntry(entry.id, (current) => ({
                                  ...current,
                                  drafts: (current.drafts ?? []).map((item) =>
                                    item.id === next.id ? next : item),
                                }))
                              }
                            />
                          ))}
                        </div>
                      )}
                      {entry.graph && (
                        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-success/25 bg-success-soft px-2.5 py-2 text-[12px] text-success-deep">
                          <Icon name="network" size={12} className="shrink-0" />
                          <span className="font-medium">Canvas updated</span>
                          <span className="font-mono text-[11px] tabular-nums">
                            {entry.graph.datasets.length} datasets ·{' '}
                            {entry.graph.edges.length} links
                          </span>
                          <button
                            type="button"
                            onClick={onClose}
                            className="ml-auto rounded px-1.5 py-0.5 font-medium text-success-deep transition-colors duration-150 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white"
                          >
                            Close and view
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>
          )}
        </div>

        <form
          onSubmit={handleSubmit}
          className="shrink-0 border-t border-line-soft bg-card p-3"
        >
          <div className="flex items-end gap-2">
            <label htmlFor="ai-chat-input" className="sr-only">
              Ask the AI assistant
            </label>
            <textarea
              ref={inputRef}
              id="ai-chat-input"
              rows={2}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              maxLength={8000}
              disabled={inputDisabled}
              placeholder={
                statusLoading
                  ? 'Checking LLM configuration…'
                  : statusError
                    ? 'Cannot read AI status; retry first'
                    : configured
                      ? 'Ask something… (tool calls are read-only; AI suggestions need manual confirmation)'
                      : 'Ask questions after configuring an LLM'
              }
              className="field-input min-h-[56px] flex-1 resize-none py-2 text-[13px] leading-5 disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={inputDisabled || !input.trim()}
              className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 active:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            >
              {sending ? (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-white/40 border-t-white" />
              ) : (
                <Icon name="send" size={14} />
              )}
              {sending ? 'Sending' : 'Send'}
            </button>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 font-mono text-[11px] text-ink-faint">
            <span>Enter to send · Shift + Enter for a new line · only the latest 50 messages are sent</span>
            <span className="tabular-nums">
              {input.length >= 8000 ? (
                <span className="text-danger-deep">{input.length}/8000</span>
              ) : (
                `${input.length}/8000`
              )}
            </span>
          </div>
        </form>
      </aside>
    </div>
  );
}
