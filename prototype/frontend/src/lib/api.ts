import type {
  AiChatMessage,
  AiChatResponse,
  AiDraftItem,
  AiEdgeKey,
  AiFocus,
  AiStatus,
  AiStreamEvent,
  AiSuggestion,
  Annotation,
  AnnotationCreatePayload,
  ChangeEntry,
  DatasetSummary,
  EdgeCreatePayload,
  EdgePatchPayload,
  FieldPatchPayload,
  ImportBatch,
  LineageEdge,
  LineageGraph,
  LoginResponse,
  PreviewResponse,
  Session,
  TargetKind,
  UserAccount,
  VersionTag,
  VersionTagDiff,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export const SESSION_STORAGE_KEY = 'lineagelite.session';
export const AUTH_EXPIRED_EVENT = 'lineagelite:auth-expired';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function readErrorDetail(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg);
          }
          return '';
        })
        .filter(Boolean);
      if (messages.length) return messages.join('; ');
    }
  }
  if (status === 401) return 'Your session has expired. Please log in again';
  if (status === 403) return 'Your account is not allowed to perform this action';
  if (status === 404) return 'The requested resource does not exist';
  if (status === 409) return 'Operation conflict. Check the current state and try again';
  if (status === 422) return 'Invalid request parameters';
  return `Request failed (HTTP ${status})`;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // Do not keep the raw text of non-JSON error bodies, to avoid showing HTML error pages to users.
    }
    if (response.status === 401 && token) {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(response.status, readErrorDetail(payload, response.status));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function loadSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === 'object' &&
      typeof (parsed as Session).access_token === 'string' &&
      typeof (parsed as Session).username === 'string' &&
      typeof (parsed as Session).role === 'string'
    ) {
      return parsed as Session;
    }
  } catch {
    // Discard corrupted local sessions.
  }
  return null;
}

export function persistSession(session: Session): void {
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Still allow the current page to use the session in private mode or when quota is exhausted.
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Cleanup failures must not block the logout flow.
  }
}

export async function login(
  username: string,
  password: string,
  signal?: AbortSignal,
): Promise<LoginResponse> {
  return request<LoginResponse>(
    '/auth/login',
    {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      signal,
    },
  );
}

export async function getDatasets(
  token: string,
  signal?: AbortSignal,
): Promise<DatasetSummary[]> {
  return request<DatasetSummary[]>('/datasets', { signal }, token);
}

export interface SubgraphParams {
  dataset: string;
  field?: string;
  hops: number;
  direction?: 'both' | 'up' | 'down';
}

export async function getSubgraph(
  token: string,
  params: SubgraphParams,
  signal?: AbortSignal,
): Promise<LineageGraph> {
  const search = new URLSearchParams({
    dataset: params.dataset,
    hops: String(params.hops),
    direction: params.direction ?? 'both',
  });
  if (params.field) search.set('field', params.field);
  return request<LineageGraph>(
    `/lineage/subgraph?${search.toString()}`,
    { signal },
    token,
  );
}

export async function getFieldPreview(
  token: string,
  datasetId: string,
  fieldName: string,
  signal?: AbortSignal,
): Promise<PreviewResponse> {
  return request<PreviewResponse>(
    `/fields/${encodeURIComponent(datasetId)}/${encodeURIComponent(fieldName)}/preview`,
    { signal },
    token,
  );
}

// ---------- M3: annotations ----------

export async function getAnnotations(
  token: string,
  targetKind: TargetKind,
  targetId: string,
  signal?: AbortSignal,
): Promise<Annotation[]> {
  const search = new URLSearchParams({
    target_kind: targetKind,
    target_id: targetId,
  });
  return request<Annotation[]>(
    `/annotations?${search.toString()}`,
    { signal },
    token,
  );
}

export async function createAnnotation(
  token: string,
  payload: AnnotationCreatePayload,
  signal?: AbortSignal,
): Promise<Annotation> {
  return request<Annotation>(
    '/annotations',
    { method: 'POST', body: JSON.stringify(payload), signal },
    token,
  );
}

// ---------- M3: field and edge editing ----------

export async function patchField(
  token: string,
  datasetId: string,
  fieldName: string,
  payload: FieldPatchPayload,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/fields/${encodeURIComponent(datasetId)}/${encodeURIComponent(fieldName)}`,
    { method: 'PATCH', body: JSON.stringify(payload), signal },
    token,
  );
}

export async function createEdge(
  token: string,
  payload: EdgeCreatePayload,
  signal?: AbortSignal,
): Promise<LineageEdge> {
  return request<LineageEdge>(
    '/edges',
    { method: 'POST', body: JSON.stringify(payload), signal },
    token,
  );
}

export async function patchEdge(
  token: string,
  edgeId: number,
  payload: EdgePatchPayload,
  signal?: AbortSignal,
): Promise<LineageEdge> {
  return request<LineageEdge>(
    `/edges/${edgeId}`,
    { method: 'PATCH', body: JSON.stringify(payload), signal },
    token,
  );
}

export async function deleteEdge(
  token: string,
  edgeId: number,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(
    `/edges/${edgeId}`,
    { method: 'DELETE', signal },
    token,
  );
}

// ---------- M3: change history and version tags ----------

export async function getChanges(
  token: string,
  entityKind: TargetKind,
  entityKey: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<ChangeEntry[]> {
  const search = new URLSearchParams({
    entity_kind: entityKind,
    entity_key: entityKey,
    limit: String(limit),
  });
  return request<ChangeEntry[]>(
    `/changes?${search.toString()}`,
    { signal },
    token,
  );
}

export async function getVersionTags(
  token: string,
  signal?: AbortSignal,
): Promise<VersionTag[]> {
  return request<VersionTag[]>('/version-tags', { signal }, token);
}

export async function createVersionTag(
  token: string,
  payload: { name: string; note?: string | null },
  signal?: AbortSignal,
): Promise<
  Pick<
    VersionTag,
    'name' | 'note' | 'change_seq' | 'created_by' | 'created_at'
  >
> {
  return request<
    Pick<
      VersionTag,
      'name' | 'note' | 'change_seq' | 'created_by' | 'created_at'
    >
  >(
    '/version-tags',
    { method: 'POST', body: JSON.stringify(payload), signal },
    token,
  );
}

export async function getVersionTagDiff(
  token: string,
  from: string,
  to: string,
  signal?: AbortSignal,
): Promise<VersionTagDiff> {
  const search = new URLSearchParams({ from, to });
  return request<VersionTagDiff>(
    `/version-tags/diff?${search.toString()}`,
    { signal },
    token,
  );
}

export async function rollbackVersionTag(
  token: string,
  name: string,
  signal?: AbortSignal,
): Promise<{ reverted: number }> {
  return request<{ reverted: number }>(
    `/version-tags/${encodeURIComponent(name)}/rollback`,
    { method: 'POST', signal },
    token,
  );
}

export async function getImportBatches(
  token: string,
  signal?: AbortSignal,
): Promise<ImportBatch[]> {
  return request<ImportBatch[]>('/import/batches', { signal }, token);
}

// ---------- User management (admin) ----------

export async function getUsers(
  token: string,
  signal?: AbortSignal,
): Promise<UserAccount[]> {
  return request<UserAccount[]>('/users', { signal }, token);
}

export async function createUser(
  token: string,
  payload: {
    username: string;
    password: string;
    display_name?: string | null;
    role: string;
  },
  signal?: AbortSignal,
): Promise<UserAccount> {
  return request<UserAccount>(
    '/users',
    { method: 'POST', body: JSON.stringify(payload), signal },
    token,
  );
}

// ---------- M4: AI assistant and heuristic lineage suggestions ----------

export async function getAiStatus(
  token: string,
  signal?: AbortSignal,
): Promise<AiStatus> {
  return request<AiStatus>('/ai/status', { signal }, token);
}

export async function sendAiChat(
  token: string,
  payload: { messages: AiChatMessage[]; focus?: AiFocus | null },
  signal?: AbortSignal,
): Promise<AiChatResponse> {
  return request<AiChatResponse>(
    '/ai/chat',
    { method: 'POST', body: JSON.stringify(payload), signal },
    token,
  );
}

export interface AiStreamHandlers {
  onEvent: (event: AiStreamEvent) => void;
}

/** SSE streaming chat (POST /ai/chat/stream): parse text/event-stream frames and invoke the callback per event. */
export async function sendAiChatStream(
  token: string,
  payload: { messages: AiChatMessage[]; focus?: AiFocus | null },
  onEvent: (event: AiStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/ai/chat/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
  }
  if (!response.ok || !response.body) {
    let payloadError: unknown = null;
    try {
      payloadError = await response.json();
    } catch {
      // Fall back to the status code when the error body is not JSON
    }
    throw new ApiError(
      response.status,
      readErrorDetail(payloadError, response.status),
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by blank lines; a data line may span chunks, so trim within the buffer
    let separator = buffer.indexOf('\n\n');
    while (separator !== -1) {
      const frame = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const dataLine = frame
        .split('\n')
        .find((line) => line.startsWith('data: '));
      if (dataLine) {
        try {
          onEvent(JSON.parse(dataLine.slice(6)) as AiStreamEvent);
        } catch {
          // Ignore unparsable frames (prevents partial/dirty frames from crashing the UI)
        }
      }
      separator = buffer.indexOf('\n\n');
    }
  }
}

export async function listDescriptionDrafts(
  token: string,
  dataset?: string | null,
  status?: 'pending' | 'accepted' | 'rejected',
  signal?: AbortSignal,
): Promise<AiDraftItem[]> {
  const params = new URLSearchParams();
  if (dataset) params.set('dataset', dataset);
  if (status) params.set('status', status);
  const query = params.toString();
  const result = await request<{ items: AiDraftItem[] }>(
    `/ai/description-drafts${query ? `?${query}` : ''}`,
    { signal },
    token,
  );
  return result.items;
}

export async function acceptDescriptionDraft(
  token: string,
  draftId: number,
  signal?: AbortSignal,
): Promise<AiDraftItem> {
  const result = await request<{ draft: AiDraftItem }>(
    `/ai/description-drafts/${draftId}/accept`,
    { method: 'POST', signal },
    token,
  );
  return result.draft;
}

export async function rejectDescriptionDraft(
  token: string,
  draftId: number,
  signal?: AbortSignal,
): Promise<void> {
  await request<void>(
    `/ai/description-drafts/${draftId}/reject`,
    { method: 'POST', signal },
    token,
  );
}

export async function suggestAiEdges(
  token: string,
  payload: { dataset: string; field?: string | null },
  signal?: AbortSignal,
): Promise<AiSuggestion[]> {
  const result = await request<{ candidates: AiSuggestion[] }>(
    '/ai/suggest',
    { method: 'POST', body: JSON.stringify(payload), signal },
    token,
  );
  return result.candidates;
}

export async function confirmAiSuggestion(
  token: string,
  key: AiEdgeKey,
  signal?: AbortSignal,
): Promise<LineageEdge> {
  const result = await request<{ edge: LineageEdge }>(
    '/ai/suggest/confirm',
    { method: 'POST', body: JSON.stringify(key), signal },
    token,
  );
  return result.edge;
}

export async function rejectAiSuggestion(
  token: string,
  key: AiEdgeKey,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(
    '/ai/suggest/reject',
    { method: 'POST', body: JSON.stringify(key), signal },
    token,
  );
}

/** Controlled download of a hosted source file; storage paths never pass through the frontend, only source file IDs are accepted. */
export async function downloadSourceFile(
  token: string,
  fileId: number,
  filename: string,
): Promise<void> {
  const response = await fetch(`${API_BASE}/files/${fileId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // Fall back to a generic message when the download fails without a parsable error body
    }
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(
      response.status,
      readErrorDetail(payload, response.status),
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
