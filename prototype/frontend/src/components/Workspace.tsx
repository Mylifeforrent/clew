import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  AiFocus,
  AiHighlightItem,
  DatasetField,
  DatasetSummary,
  EdgeDraft,
  FieldSelection,
  LineageDataset,
  LineageEdge,
  LineageGraph,
  Session,
} from '../types';
import {
  ApiError,
  deleteEdge,
  getDatasets,
  getSubgraph,
  isAbortError,
} from '../lib/api';
import { edgeEntityKey } from '../lib/entities';
import { isAdmin, isEditor } from '../lib/roles';
import { TopBar } from './TopBar';
import { DatasetSidebar } from './DatasetSidebar';
import { LineageCanvas } from './LineageCanvas';
import { DetailPanel } from './DetailPanel';
import { EdgeDetailPanel } from './EdgeDetailPanel';
import { PreviewModal } from './PreviewModal';
import { EdgeCreateModal } from './EdgeCreateModal';
import { ConfirmDialog } from './ConfirmDialog';
import { VersionDrawer } from './VersionDrawer';
import { AiAssistantDrawer } from './AiAssistantDrawer';
import { UserManagementModal } from './UserManagementModal';
import { Toast } from './Toast';
import type { ToastMessage, ToastTone } from './Toast';

interface WorkspaceProps {
  session: Session;
  onLogout: () => void;
}

function errorMessage(reason: unknown, fallback: string): string {
  if (reason instanceof ApiError) return reason.message;
  return fallback;
}

export function Workspace({ session, onLogout }: WorkspaceProps) {
  const canEdit = isEditor(session.role);
  const admin = isAdmin(session.role);

  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [datasetsReloadKey, setDatasetsReloadKey] = useState(0);

  const [search, setSearch] = useState('');
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [hops, setHops] = useState(3);

  const [graph, setGraph] = useState<LineageGraph | null>(null);
  // Subgraph returned by the AI chat: shown in preference to the graph fetched for the
  // selected dataset; cleared when the dataset/hops/refresh change, returning to the normal subgraph logic.
  const [aiGraph, setAiGraph] = useState<LineageGraph | null>(null);
  // Highlight fields declared by AI answers (mark_highlight): seq distinguishes each
  // answer round; an empty fields array means the new answer declared no highlights
  // (the canvas should clear the trace state).
  const [aiFieldFocus, setAiFieldFocus] = useState<{
    seq: number;
    fields: AiHighlightItem[];
  } | null>(null);
  const aiFocusSeq = useRef(0);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphReloadKey, setGraphReloadKey] = useState(0);

  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [fieldsExpandedIds, setFieldsExpandedIds] = useState<Set<string>>(
    () => new Set(),
  );
  // Canvas filter conditions (design doc §5.1: confidence / edit source)
  const [minConfidence, setMinConfidence] = useState(0);
  const [hideAiEdges, setHideAiEdges] = useState(false);
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [selectedField, setSelectedField] = useState<FieldSelection | null>(
    null,
  );
  const [selectedEdgeId, setSelectedEdgeId] = useState<number | null>(null);
  const [edgeStartEditing, setEdgeStartEditing] = useState(false);
  const [previewSelection, setPreviewSelection] =
    useState<FieldSelection | null>(null);

  // M3: new-edge draft, delete confirmation, versions drawer, user management
  const [edgeDraft, setEdgeDraft] = useState<EdgeDraft | null>(null);
  const [pendingDeleteEdge, setPendingDeleteEdge] = useState<LineageEdge | null>(
    null,
  );
  const [deletingEdge, setDeletingEdge] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [usersOpen, setUsersOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastTimer = useRef<number | null>(null);
  const toastSeq = useRef(1);

  const showToast = useCallback((message: string, tone: ToastTone = 'info') => {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    setToast({ id: toastSeq.current, message, tone });
    toastSeq.current += 1;
    toastTimer.current = window.setTimeout(() => {
      setToast(null);
      toastTimer.current = null;
    }, 4200);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    };
  }, []);

  /** Apply a GraphPayload uniformly: the regular subgraph and AI graphs share the same canvas state cleanup. */
  const applyGraph = useCallback((payload: LineageGraph) => {
    setGraph(payload);
    setCollapsedIds((current) => {
      const retained = new Set(
        payload.datasets
          .map((dataset) => dataset.id)
          .filter((id) => current.has(id)),
      );
      return retained.size === current.size ? current : retained;
    });
    setFieldsExpandedIds((current) => {
      const retained = new Set(
        payload.datasets
          .map((dataset) => dataset.id)
          .filter((id) => current.has(id)),
      );
      return retained.size === current.size ? current : retained;
    });
    setSelectedField((current) => {
      if (!current) return null;
      const dataset = payload.datasets.find(
        (item) => item.id === current.dataset.id,
      );
      const field = dataset?.fields.find(
        (item) => item.name === current.field.name,
      );
      return dataset && field ? { dataset, field } : null;
    });
    setSelectedEdgeId((current) =>
      current !== null && payload.edges.some((edge) => edge.id === current)
        ? current
        : null,
    );
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setDatasetsLoading(true);
    setDatasetsError(null);

    getDatasets(session.access_token, controller.signal)
      .then((list) => {
        if (controller.signal.aborted) return;
        setDatasets(list);
        setSelectedDatasetId((current) => {
          if (current && list.some((dataset) => dataset.id === current)) {
            return current;
          }
          return list[0]?.id ?? null;
        });
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || isAbortError(reason)) return;
        setDatasetsError(
          errorMessage(reason, 'Unable to load the dataset list; check whether the backend service is running'),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setDatasetsLoading(false);
      });

    return () => controller.abort();
  }, [session.access_token, datasetsReloadKey]);

  useEffect(() => {
    // Leave the AI graph override when the dataset, hops or refresh change, returning to the normal subgraph logic.
    setAiGraph(null);
    if (!selectedDatasetId) {
      setGraph(null);
      setGraphError(null);
      setGraphLoading(false);
      return;
    }

    const controller = new AbortController();
    setGraphLoading(true);
    setGraphError(null);

    getSubgraph(
      session.access_token,
      { dataset: selectedDatasetId, hops, direction: 'both' },
      controller.signal,
    )
      .then((payload) => {
        if (controller.signal.aborted) return;
        applyGraph(payload);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || isAbortError(reason)) return;
        setGraphError(
          errorMessage(reason, 'Unable to load the lineage subgraph. Please try again later'),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setGraphLoading(false);
      });

    return () => controller.abort();
  }, [applyGraph, session.access_token, selectedDatasetId, hops, graphReloadKey]);

  /** The graph the canvas finally shows: the AI subgraph wins until the user changes the dataset/hops or refreshes. */
  const displayGraph = aiGraph ?? graph;

  const visibleDatasets = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return datasets;
    return datasets.filter(
      (dataset) =>
        dataset.id.toLowerCase().includes(query) ||
        dataset.name.toLowerCase().includes(query) ||
        (dataset.field_names ?? []).some((name) =>
          name.toLowerCase().includes(query),
        ),
    );
  }, [datasets, search]);

  // Filters only affect the canvas/edge list and never modify the subgraph data returned by the backend
  const filteredGraph = useMemo(() => {
    if (!displayGraph) return null;
    if (!minConfidence && !hideAiEdges && !confirmedOnly) return displayGraph;
    const edges = displayGraph.edges.filter((edge) => {
      if ((hideAiEdges || confirmedOnly) && edge.source === 'ai') return false;
      if (minConfidence > 0 && (edge.confidence ?? 1) < minConfidence) {
        return false;
      }
      return true;
    });
    return edges.length === displayGraph.edges.length
      ? displayGraph
      : { ...displayGraph, edges };
  }, [displayGraph, minConfidence, hideAiEdges, confirmedOnly]);

  // Edge details use the unfiltered original subgraph so canvas filters do not hide the edge being viewed
  const selectedEdge = useMemo(
    () => displayGraph?.edges.find((edge) => edge.id === selectedEdgeId) ?? null,
    [displayGraph, selectedEdgeId],
  );

  const refreshGraph = useCallback(() => {
    setAiGraph(null);
    setAiFieldFocus(null);
    setGraphReloadKey((value) => value + 1);
  }, []);

  const refreshAll = useCallback(() => {
    setAiGraph(null);
    setAiFieldFocus(null);
    setDatasetsReloadKey((value) => value + 1);
    setGraphReloadKey((value) => value + 1);
    setSelectedEdgeId(null);
    setEdgeStartEditing(false);
  }, []);

  const handleSelectDataset = useCallback((datasetId: string) => {
    setAiGraph(null);
    setAiFieldFocus(null);
    setSelectedDatasetId(datasetId);
    setSelectedField(null);
    setSelectedEdgeId(null);
    setEdgeStartEditing(false);
    setCollapsedIds(new Set());
    setFieldsExpandedIds(new Set());
    setGraphError(null);
  }, []);

  const handleHopsChange = useCallback((nextHops: number) => {
    setAiGraph(null);
    setAiFieldFocus(null);
    setHops(nextHops);
  }, []);

  const handleToggleCollapse = useCallback((datasetId: string) => {
    setCollapsedIds((current) => {
      const next = new Set(current);
      if (next.has(datasetId)) next.delete(datasetId);
      else next.add(datasetId);
      return next;
    });
  }, []);

  const handleToggleFields = useCallback((datasetId: string) => {
    setFieldsExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(datasetId)) next.delete(datasetId);
      else next.add(datasetId);
      return next;
    });
  }, []);

  const handleToggleAll = useCallback(() => {
    if (!displayGraph) return;
    setCollapsedIds((current) => {
      const allCollapsed = displayGraph.datasets.every((dataset) =>
        current.has(dataset.id),
      );
      if (allCollapsed) return new Set();
      return new Set(displayGraph.datasets.map((dataset) => dataset.id));
    });
  }, [displayGraph]);

  const aiFocus = useMemo<AiFocus | null>(() => {
    if (selectedField) {
      return {
        dataset: selectedField.dataset.id,
        field: selectedField.field.name,
      };
    }
    if (selectedDatasetId) return { dataset: selectedDatasetId };
    return null;
  }, [selectedField, selectedDatasetId]);

  /** AI answer linking: switch the subgraph and hand the mark_highlight declarations to the canvas for trace highlighting. */
  const handleAiGraph = useCallback(
    (payload: LineageGraph | null, highlights?: AiHighlightItem[]) => {
      aiFocusSeq.current += 1;
      setAiFieldFocus({
        seq: aiFocusSeq.current,
        fields: highlights ?? [],
      });
      if (!payload) return;
      setAiGraph(payload);
      applyGraph(payload);
      setGraphError(null);
      showToast(
        `Canvas updated: ${payload.datasets.length} datasets · ${payload.edges.length} links`,
        'success',
      );
    },
    [applyGraph, showToast],
  );

  const handleSelectField = useCallback(
    (dataset: LineageDataset, field: DatasetField) => {
      setSelectedField({ dataset, field });
      setSelectedEdgeId(null);
      setEdgeStartEditing(false);
    },
    [],
  );

  const handleCloseField = useCallback(() => setSelectedField(null), []);

  const handleSelectEdge = useCallback(
    (edge: LineageEdge, options?: { edit?: boolean }) => {
      setSelectedField(null);
      setSelectedEdgeId(edge.id);
      setEdgeStartEditing(Boolean(options?.edit));
    },
    [],
  );

  const handleCloseEdge = useCallback(() => {
    setSelectedEdgeId(null);
    setEdgeStartEditing(false);
  }, []);

  const handleOpenPreview = useCallback((selection: FieldSelection) => {
    setPreviewSelection(selection);
  }, []);
  const handleClosePreview = useCallback(() => setPreviewSelection(null), []);

  const handleRequestDeleteEdge = useCallback((edge: LineageEdge) => {
    setPendingDeleteEdge(edge);
  }, []);

  const handleConfirmDeleteEdge = useCallback(async () => {
    if (!pendingDeleteEdge || deletingEdge) return;
    setDeletingEdge(true);
    try {
      await deleteEdge(session.access_token, pendingDeleteEdge.id);
      showToast(`Deleted lineage edge #${pendingDeleteEdge.id}`, 'success');
      if (selectedEdgeId === pendingDeleteEdge.id) {
        setSelectedEdgeId(null);
        setEdgeStartEditing(false);
      }
      refreshGraph();
    } catch (reason) {
      showToast(
        reason instanceof ApiError
          ? reason.message
          : 'Failed to delete the lineage edge. Please try again later.',
        'error',
      );
    } finally {
      setDeletingEdge(false);
      setPendingDeleteEdge(null);
    }
  }, [
    deletingEdge,
    pendingDeleteEdge,
    refreshGraph,
    selectedEdgeId,
    session.access_token,
    showToast,
  ]);

  const handleConnectRequest = useCallback((draft: EdgeDraft) => {
    setEdgeDraft(draft);
  }, []);

  const handleEdgeCreated = useCallback(
    (edge: LineageEdge) => {
      setEdgeDraft(null);
      setSelectedField(null);
      setSelectedEdgeId(edge.id);
      setEdgeStartEditing(false);
      showToast(`Added lineage edge #${edge.id} (manual edge)`, 'success');
      refreshGraph();
    },
    [refreshGraph, showToast],
  );

  const handleCanvasNotice = useCallback(
    (message: string) => showToast(message, 'error'),
    [showToast],
  );

  /** After suggest_lineage persists candidates in the chat: refresh the canvas (blue dashed candidate edges) and notify. */
  const handleAiSuggested = useCallback(
    (count: number) => {
      refreshGraph();
      showToast(`AI stored ${count} lineage candidate edges; confirm them manually on the canvas`, 'info');
    },
    [refreshGraph, showToast],
  );

  /** Clicking an evidence anchor in an answer: apply that field as the canvas trace focus (incrementing seq triggers application). */
  const handleAiFieldFocus = useCallback((dataset: string, field: string) => {
    aiFocusSeq.current += 1;
    setAiFieldFocus({
      seq: aiFocusSeq.current,
      fields: [{ dataset, field }],
    });
  }, []);

  const handleFieldUpdated = useCallback(() => {
    refreshGraph();
  }, [refreshGraph]);

  const retryDatasets = useCallback(() => {
    setDatasetsReloadKey((value) => value + 1);
  }, []);
  const retryGraph = useCallback(() => {
    setGraphReloadKey((value) => value + 1);
  }, []);

  /** When the originally selected dataset is not in the AI graph, use a node from that graph as the canvas seed. */
  const canvasSeedId = useMemo(() => {
    if (!aiGraph) return selectedDatasetId;
    const preferred = aiFocus?.dataset;
    if (preferred && aiGraph.datasets.some((item) => item.id === preferred)) {
      return preferred;
    }
    return aiGraph.datasets[0]?.id ?? null;
  }, [aiFocus, aiGraph, selectedDatasetId]);

  const deleteDescription = pendingDeleteEdge
    ? `${edgeEntityKey(pendingDeleteEdge)} (source ${pendingDeleteEdge.source})`
    : '';

  return (
    <div className="flex min-h-dvh flex-col bg-page xl:h-dvh xl:overflow-hidden">
      <TopBar
        session={session}
        search={search}
        onSearchChange={setSearch}
        datasetCount={datasets.length}
        visibleCount={visibleDatasets.length}
        hops={hops}
        onHopsChange={handleHopsChange}
        graphLoading={graphLoading}
        aiOpen={aiOpen}
        onOpenAi={() => setAiOpen(true)}
        onOpenVersions={() => setVersionsOpen(true)}
        onOpenUsers={() => {
          if (admin) setUsersOpen(true);
        }}
        onLogout={onLogout}
      />

      <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
        <DatasetSidebar
          datasets={datasets}
          visibleDatasets={visibleDatasets}
          selectedId={selectedDatasetId}
          loading={datasetsLoading}
          error={datasetsError}
          search={search}
          hops={hops}
          graph={filteredGraph}
          minConfidence={minConfidence}
          hideAiEdges={hideAiEdges}
          confirmedOnly={confirmedOnly}
          onMinConfidenceChange={setMinConfidence}
          onHideAiEdgesChange={setHideAiEdges}
          onConfirmedOnlyChange={setConfirmedOnly}
          onSelect={handleSelectDataset}
          onRetry={retryDatasets}
          onClearSearch={() => setSearch('')}
        />

        <main className="relative flex min-h-[560px] flex-1 flex-col overflow-hidden xl:min-h-0">
          <div className="relative min-h-0 flex-1">
            <LineageCanvas
              graph={filteredGraph}
              seedDatasetId={canvasSeedId}
              hops={hops}
              loading={graphLoading}
              error={graphError}
              canEdit={canEdit}
              collapsedIds={collapsedIds}
              fieldsExpandedIds={fieldsExpandedIds}
              onToggleCollapse={handleToggleCollapse}
              onToggleFields={handleToggleFields}
              onToggleAll={handleToggleAll}
              onSelectField={handleSelectField}
              onSelectEdge={handleSelectEdge}
              onRequestDeleteEdge={handleRequestDeleteEdge}
              onConnectRequest={handleConnectRequest}
              onNotice={handleCanvasNotice}
              onRetry={retryGraph}
              aiFocusFields={aiFieldFocus}
            />
          </div>
        </main>

        {selectedEdge ? (
          <EdgeDetailPanel
            edge={selectedEdge}
            token={session.access_token}
            canEdit={canEdit}
            startEditing={edgeStartEditing}
            onClose={handleCloseEdge}
            onRequestDelete={handleRequestDeleteEdge}
            onRefresh={handleFieldUpdated}
            onNotify={showToast}
          />
        ) : (
          <DetailPanel
            selection={selectedField}
            graph={filteredGraph}
            token={session.access_token}
            canEdit={canEdit}
            onClose={handleCloseField}
            onPreview={handleOpenPreview}
            onRefresh={handleFieldUpdated}
            onNotify={showToast}
          />
        )}
      </div>

      {previewSelection && (
        <PreviewModal
          key={`${previewSelection.dataset.id}.${previewSelection.field.name}`}
          selection={previewSelection}
          token={session.access_token}
          onClose={handleClosePreview}
        />
      )}

      {edgeDraft && (
        <EdgeCreateModal
          key={`${edgeDraft.from_dataset}.${edgeDraft.from_field ?? '*'}-${edgeDraft.to_dataset}.${edgeDraft.to_field ?? '*'}`}
          draft={edgeDraft}
          token={session.access_token}
          onClose={() => setEdgeDraft(null)}
          onCreated={handleEdgeCreated}
        />
      )}

      <ConfirmDialog
        open={Boolean(pendingDeleteEdge)}
        title="Delete lineage edge"
        danger
        busy={deletingEdge}
        confirmLabel="Confirm delete"
        message={
          <div className="space-y-1.5">
            <p className="break-all font-mono text-[11px] text-ink-soft">
              {deleteDescription}
            </p>
            <p>Deletion is written to the change log; to restore it, an administrator can roll back to an earlier version tag.</p>
          </div>
        }
        onConfirm={handleConfirmDeleteEdge}
        onCancel={() => {
          if (!deletingEdge) setPendingDeleteEdge(null);
        }}
      />

      {versionsOpen && (
        <VersionDrawer
          token={session.access_token}
          role={session.role}
          onClose={() => setVersionsOpen(false)}
          onDataChanged={refreshAll}
          onNotify={showToast}
        />
      )}

      <AiAssistantDrawer
        open={aiOpen}
        token={session.access_token}
        focus={aiFocus}
        canEdit={canEdit}
        onClose={() => setAiOpen(false)}
        onGraph={handleAiGraph}
        onSuggested={handleAiSuggested}
        onFieldFocus={handleAiFieldFocus}
      />

      {usersOpen && admin && (
        <UserManagementModal
          token={session.access_token}
          currentUsername={session.username}
          onClose={() => setUsersOpen(false)}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
