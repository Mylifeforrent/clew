import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import type {
  Connection,
  OnSelectionChangeParams,
  ReactFlowInstance,
} from '@xyflow/react';
import type {
  AiHighlightItem,
  DatasetField,
  EdgeDraft,
  LineageDataset,
  LineageEdge,
  LineageGraph,
} from '../types';
import { EDGE_COLORS, withAlpha } from '../lib/edgeColors';
import {
  computeFieldChain,
  deriveFieldMatches,
  derivedLinkKey,
} from '../lib/fieldChain';
import type { FieldChain } from '../lib/fieldChain';
import { FIELD_PREVIEW_LIMIT, layoutDatasets, NODE_WIDTH } from '../lib/layout';
import {
  TABLE_SOURCE_HANDLE,
  TABLE_TARGET_HANDLE,
  fieldSourceHandle,
  fieldTargetHandle,
} from '../lib/handles';
import { DatasetNode } from './DatasetNode';
import type { DatasetFlowNode } from './DatasetNode';
import { GroupNode } from './GroupNode';
import type { GroupFlowNode } from './GroupNode';
import {
  LineageEdgeView,
  getEdgeVisual,
} from './LineageEdge';
import type { EdgeKind, LineageEdgeData, LineageFlowEdge } from './LineageEdge';
import { SourceBadge } from './SourceBadge';
import { Icon } from './Icon';
import { formatConfidence } from '../lib/format';
import { useI18n } from '../i18n';

const nodeTypes = { dataset: DatasetNode, group: GroupNode };
const edgeTypes = { lineage: LineageEdgeView };

/** When trace focus is active, links that miss the chain are dimmed to this opacity */
const DIMMED_OPACITY = 0.15;
const DIMMED_MARKER_ALPHA = 0.3;

/** R16: default maximum number of edge-list rows */
const EDGE_LIST_LIMIT = 20;
/** R15: read-state memory for the mobile hint overlay below md */
const MOBILE_HINTS_STORAGE_KEY = 'clew.canvasMobileHintsRead';
/**
 * R16: the bottom Controls (3 × 27px buttons + border ≈ 83px, panel margin 15px) occupy the bottom-left,
 * so the edge-list overlay moves just above them.
 */
const EDGE_LIST_PANEL_CLASS = '!mb-[104px]';
/** R16: expanded edge-list width; very narrow canvases keep the panel margin (underscore = space inside calc) */
const EDGE_LIST_WIDTH_CLASS = 'w-[min(300px,calc(100%_-_30px))]';

type FlowNode = DatasetFlowNode | GroupFlowNode;

interface FieldFocus {
  datasetId: string;
  fieldName: string;
}

interface CollapsedGroup {
  id: string;
  memberIds: string[];
  label: string;
}

interface AggregateEdge {
  sourceNode: string;
  targetNode: string;
  sourceLabel: string;
  targetLabel: string;
  edge: LineageEdge;
  count: number;
}

/** R16: edge-list row (stored lineage edge + display label + whether it connects directly to the traced focus field) */
interface EdgeListRow {
  edge: LineageEdge;
  fromLabel: string;
  toLabel: string;
  connectedToFocus: boolean;
}

interface LineageCanvasProps {
  graph: LineageGraph | null;
  seedDatasetId: string | null;
  hops: number;
  loading: boolean;
  error: string | null;
  canEdit: boolean;
  /** R15.2: whether the dataset list (Workspace sidebar source) is loading — the empty first screen shows a loading card instead of the empty state */
  datasetsLoading: boolean;
  /** R15.3: edge count of the parent graph before filtering — shows the filtered-empty hint when filtering clears all edges but the parent graph has some */
  totalEdgeCount: number;
  collapsedIds: ReadonlySet<string>;
  fieldsExpandedIds: ReadonlySet<string>;
  onToggleCollapse: (datasetId: string) => void;
  onToggleFields: (datasetId: string) => void;
  onToggleAll: () => void;
  onSelectField: (dataset: LineageDataset, field: DatasetField) => void;
  onSelectEdge: (edge: LineageEdge, options?: { edit?: boolean }) => void;
  onRequestDeleteEdge: (edge: LineageEdge) => void;
  onConnectRequest: (draft: EdgeDraft) => void;
  onNotice: (message: string) => void;
  onRetry: () => void;
  /**
   * Highlight fields declared by AI answers (mark_highlight aggregate): a seq change applies or clears
   * the trace focus; an empty fields array means an explicit clear (the new answer declared no highlights).
   */
  aiFocusFields: { seq: number; fields: AiHighlightItem[] } | null;
}

const EMPTY_NODES: FlowNode[] = [];
const EMPTY_EDGES: LineageFlowEdge[] = [];

function parseFieldHandle(
  handleId: string | null,
  prefix: string,
): string | null {
  if (!handleId || !handleId.startsWith(prefix)) return null;
  const name = handleId.slice(prefix.length);
  return name || null;
}

function sameStringList(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((value, index) => value === b[index]);
}

/**
 * R15: determine trace state from edge data (branch-for-branch equivalent to the pre-refactor effect):
 * derived lines use linkKeys, real field-level edges use edgeIds, real table-level and aggregate edges are always dim.
 */
function edgeFocusStateOf(
  data: LineageEdgeData,
  chain: FieldChain,
): 'chain' | 'dim' {
  if (data.derived) {
    return data.derivedLinkKey && chain.linkKeys.has(data.derivedLinkKey)
      ? 'chain'
      : 'dim';
  }
  if (data.aggregateCount) return 'dim';
  if (data.kind === 'field' && data.edge) {
    return chain.edgeIds.has(data.edge.id) ? 'chain' : 'dim';
  }
  return 'dim';
}

/**
 * R15: "shallow-patch" the trace state onto a single edge — only rewrite focusState/stroke/opacity/
 * animated/marker/zIndex, the fields that change with coloring; callback references inside data are kept as-is.
 * Every branch value corresponds one-to-one with the pre-refactor effect.
 */
function applyEdgeFocus(
  edge: LineageFlowEdge,
  focusState: 'chain' | 'dim',
): LineageFlowEdge {
  const data = edge.data as LineageEdgeData;

  if (data.derived) {
    const strokeColor =
      focusState === 'chain' ? EDGE_COLORS.focus : EDGE_COLORS.derived;
    return {
      ...edge,
      data: { ...data, focusState },
      style: {
        ...edge.style,
        stroke: strokeColor,
        strokeWidth: focusState === 'chain' ? 2.6 : 1.3,
        strokeDasharray: '2 4',
        opacity: focusState === 'chain' ? 1 : DIMMED_OPACITY,
      },
      animated: focusState === 'chain',
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color:
          focusState === 'dim'
            ? withAlpha(EDGE_COLORS.derived, DIMMED_MARKER_ALPHA)
            : strokeColor,
        width: 13,
        height: 13,
      },
      zIndex: focusState === 'chain' ? 2 : 0,
    };
  }

  if (!data.edge) return edge;
  const visual = getEdgeVisual(data.edge);

  if (data.kind === 'field') {
    const strokeColor =
      focusState === 'chain' ? EDGE_COLORS.focus : visual.color;
    return {
      ...edge,
      data: { ...data, focusState },
      style: {
        ...edge.style,
        stroke: strokeColor,
        strokeWidth: focusState === 'chain' ? 2.6 : visual.width,
        strokeDasharray: visual.dash,
        opacity: focusState === 'chain' ? 1 : DIMMED_OPACITY,
      },
      animated: focusState === 'chain' ? true : visual.isAi,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color:
          focusState === 'dim'
            ? withAlpha(visual.color, DIMMED_MARKER_ALPHA)
            : strokeColor,
        width: 15,
        height: 15,
      },
      zIndex: focusState === 'chain' ? 2 : 0,
    };
  }

  // kind 'table': real table-level edges and cross-group aggregate edges
  const isAggregate = Boolean(data.aggregateCount);
  return {
    ...edge,
    data: { ...data, focusState },
    style: {
      ...edge.style,
      stroke: visual.color,
      strokeWidth: isAggregate ? 1.5 : visual.width,
      strokeDasharray: isAggregate ? visual.dash ?? '5 4' : visual.dash,
      opacity: DIMMED_OPACITY,
    },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: withAlpha(visual.color, DIMMED_MARKER_ALPHA),
      width: 15,
      height: 15,
    },
    zIndex: 0,
  };
}

export function LineageCanvas({
  graph,
  seedDatasetId,
  hops,
  loading,
  error,
  canEdit,
  datasetsLoading,
  totalEdgeCount,
  collapsedIds,
  fieldsExpandedIds,
  onToggleCollapse,
  onToggleFields,
  onToggleAll,
  onSelectField,
  onSelectEdge,
  onRequestDeleteEdge,
  onConnectRequest,
  onNotice,
  onRetry,
  aiFocusFields,
}: LineageCanvasProps) {
  const { t } = useI18n();
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<LineageFlowEdge>([]);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<
    FlowNode,
    LineageFlowEdge
  > | null>(null);
  // Node positions after manual dragging: reused first when folding/refreshing rebuilds nodes, avoiding dagre overwrites
  const draggedPositions = useRef(new Map<string, { x: number; y: number }>());
  const [groups, setGroups] = useState<CollapsedGroup[]>([]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const nextGroupId = useRef(1);
  // Field trace focus: after clicking a field row or an AI declaration, highlight the whole chain along field-level links
  const [focusFields, setFocusFields] = useState<FieldFocus[]>([]);
  // R16: edge-list overlay (collapsed by default so it does not cover the bottom Controls)
  const [edgeListOpen, setEdgeListOpen] = useState(false);
  const [edgeListQuery, setEdgeListQuery] = useState('');
  // R15: first-visit hint overlay below md (read state remembered in localStorage)
  const [mobileHintsDismissed, setMobileHintsDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(MOBILE_HINTS_STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  });

  // View-derived: same-name field match lines from table-level lineage (not stored lineage; trace demo only)
  const derivedLinks = useMemo(
    () => (graph ? deriveFieldMatches(graph) : []),
    [graph],
  );
  const chain = useMemo(
    () =>
      graph && focusFields.length > 0
        ? computeFieldChain(graph, derivedLinks, focusFields)
        : null,
    [graph, derivedLinks, focusFields],
  );

  // M2 follow-up fix: a seed or hop change counts as a new graph — clear drag positions and groups
  // so dagre re-layouts for the new subgraph size, avoiding old/new node position overlap.
  useEffect(() => {
    draggedPositions.current.clear();
    setGroups([]);
    setSelectedNodeIds([]);
    setFocusFields([]);
    nextGroupId.current = 1;
  }, [seedDatasetId, hops]);

  // After a subgraph refresh, drop focus fields that no longer exist (all gone = clear the trace state)
  useEffect(() => {
    if (focusFields.length === 0 || !graph) return;
    const next = focusFields.filter((item) => {
      const dataset = graph.datasets.find((d) => d.id === item.datasetId);
      return Boolean(
        dataset?.fields.some((f) => f.name === item.fieldName),
      );
    });
    if (next.length !== focusFields.length) setFocusFields(next);
  }, [graph, focusFields]);

  // After a subgraph refresh, drop group members that no longer exist
  useEffect(() => {
    if (!graph) {
      setGroups([]);
      setSelectedNodeIds([]);
      return;
    }
    const present = new Set(graph.datasets.map((dataset) => dataset.id));
    setSelectedNodeIds((previous) => {
      const next = previous.filter((id) => present.has(id));
      return next.length === previous.length ? previous : next;
    });
    setGroups((previous) => {
      const next = previous
        .map((group) => ({
          ...group,
          memberIds: group.memberIds.filter((id) => present.has(id)),
        }))
        .filter((group) => group.memberIds.length >= 2);
      const unchanged =
        next.length === previous.length &&
        next.every(
          (group, index) =>
            group.id === previous[index].id &&
            group.memberIds.length === previous[index].memberIds.length,
        );
      return unchanged ? previous : next;
    });
  }, [graph]);

  const handleNodeDragStop = useCallback((_: unknown, node: FlowNode) => {
    draggedPositions.current.set(node.id, { ...node.position });
  }, []);

  const handleExpandGroup = useCallback((groupId: string) => {
    draggedPositions.current.delete(groupId);
    setGroups((previous) => previous.filter((group) => group.id !== groupId));
  }, []);

  const handleSelectionChange = useCallback(
    (params: OnSelectionChangeParams<FlowNode, LineageFlowEdge>) => {
      const ids = params.nodes
        .filter((node) => node.type === 'dataset')
        .map((node) => node.id);
      if (ids.length > 0) setFocusFields([]);
      setSelectedNodeIds((previous) => {
        const same =
          previous.length === ids.length &&
          previous.every((id) => ids.includes(id));
        return same ? previous : ids;
      });
    },
    [],
  );

  const handleCollapseSelected = useCallback(() => {
    if (selectedNodeIds.length < 2) return;
    const nameById = new Map(
      (graph?.datasets ?? []).map((dataset) => [
        dataset.id,
        dataset.name || dataset.id,
      ]),
    );
    const names = selectedNodeIds.map((id) => nameById.get(id) ?? id);
    const joiner = t('canvas.groupNameJoin');
    const label =
      names.length > 2
        ? t('canvas.groupLabelMore', {
            names: names.slice(0, 2).join(joiner),
            rest: names.length - 2,
          })
        : names.join(joiner);
    const groupId = `group-${nextGroupId.current}`;
    nextGroupId.current += 1;

    const positions = new Map<string, { x: number; y: number }>(
      nodes
        .filter((node): node is DatasetFlowNode => node.type === 'dataset')
        .map((node) => [node.id, node.position] as const),
    );
    const memberPositions = selectedNodeIds
      .map((id) => positions.get(id))
      .filter((position): position is { x: number; y: number } =>
        Boolean(position),
      );
    if (memberPositions.length >= 2) {
      const centerX =
        memberPositions.reduce((sum, position) => sum + position.x, 0) /
        memberPositions.length;
      const centerY =
        memberPositions.reduce((sum, position) => sum + position.y, 0) /
        memberPositions.length;
      draggedPositions.current.set(groupId, {
        x: centerX + NODE_WIDTH / 2 - 124,
        y: centerY + 70,
      });
    }

    setGroups((previous) => [
      ...previous,
      { id: groupId, memberIds: selectedNodeIds, label },
    ]);
    setSelectedNodeIds([]);
    setNodes((current) =>
      current.map((node) =>
        node.selected ? { ...node, selected: false } : node,
      ),
    );
    setEdges((current) =>
      current.map((edge) =>
        edge.selected ? { ...edge, selected: false } : edge,
      ),
    );
  }, [graph, nodes, selectedNodeIds, setEdges, setNodes, t]);

  /** Ensure chain fields are visible before tracing: collapsed datasets expand automatically, and field lists beyond the preview limit expand automatically */
  const revealChainFields = useCallback(
    (targetChain: FieldChain) => {
      if (!graph) return;
      targetChain.nodes.forEach((node) => {
        if (collapsedIds.has(node.datasetId)) onToggleCollapse(node.datasetId);
        const target = graph.datasets.find(
          (item) => item.id === node.datasetId,
        );
        if (!target) return;
        const visibleCount = fieldsExpandedIds.has(node.datasetId)
          ? target.fields.length
          : Math.min(target.fields.length, FIELD_PREVIEW_LIMIT);
        const index = target.fields.findIndex(
          (item) => item.name === node.fieldName,
        );
        if (index >= visibleCount) onToggleFields(node.datasetId);
      });
    },
    [collapsedIds, fieldsExpandedIds, graph, onToggleCollapse, onToggleFields],
  );

  // Mirror ref of the trace focus: handleSelectField no longer depends on focusFields state
  // and its reference stays stable — callbacks in node data do not change with trace state, which is the premise of the memo split.
  const focusFieldsRef = useRef<FieldFocus[]>([]);
  focusFieldsRef.current = focusFields;

  const handleSelectField = useCallback(
    (dataset: LineageDataset, field: DatasetField) => {
      setSelectedNodeIds([]);
      setNodes((current) => {
        const hasSelected = current.some((node) => node.selected);
        return hasSelected
          ? current.map((node) => ({ ...node, selected: false }))
          : current;
      });
      setEdges((current) => {
        const hasSelected = current.some((edge) => edge.selected);
        return hasSelected
          ? current.map((edge) => ({ ...edge, selected: false }))
          : current;
      });

      const nextFocus: FieldFocus[] = [
        { datasetId: dataset.id, fieldName: field.name },
      ];
      const current = focusFieldsRef.current;
      const sameFocus =
        current.length === 1 &&
        current[0].datasetId === nextFocus[0].datasetId &&
        current[0].fieldName === nextFocus[0].fieldName;
      setFocusFields(nextFocus);

      // Make sure the chain's field rows are visible before tracing, otherwise chain lines stay hidden.
      if (graph && !sameFocus) {
        const nextChain = computeFieldChain(graph, derivedLinks, nextFocus);
        if (nextChain) revealChainFields(nextChain);
      }

      onSelectField(dataset, field);
    },
    [
      derivedLinks,
      graph,
      revealChainFields,
      onSelectField,
      setEdges,
      setNodes,
    ],
  );

  const handleEdgeClick = useCallback(
    (_: unknown, edge: LineageFlowEdge) => {
      const data = edge.data;
      if (!data?.edge || data.aggregateCount || data.derived) return;
      setFocusFields([]);
      onSelectEdge(data.edge);
    },
    [onSelectEdge],
  );

  const handlePaneClick = useCallback(() => setFocusFields([]), []);

  // Highlight fields declared by AI answers: validate existence → auto-expand the chain → apply as trace focus
  useEffect(() => {
    if (!aiFocusFields) return;
    if (aiFocusFields.fields.length === 0) {
      setFocusFields([]);
      return;
    }
    if (!graph) return;
    const valid = aiFocusFields.fields.filter((item) => {
      const dataset = graph.datasets.find((d) => d.id === item.dataset);
      return Boolean(dataset?.fields.some((f) => f.name === item.field));
    });
    if (valid.length === 0) return;
    const nextFocus = valid.map((item) => ({
      datasetId: item.dataset,
      fieldName: item.field,
    }));
    const nextChain = computeFieldChain(graph, derivedLinks, nextFocus);
    if (!nextChain) return;
    revealChainFields(nextChain);
    setFocusFields(nextFocus);
  }, [aiFocusFields, graph, derivedLinks, revealChainFields]);

  const handleNodeClick = useCallback(
    (_: unknown, node: FlowNode) => {
      if (node.type === 'group') handleExpandGroup(node.id);
    },
    [handleExpandGroup],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      const { source, target, sourceHandle, targetHandle } = connection;
      if (!source || !target || !sourceHandle || !targetHandle) return;
      if (source === target && sourceHandle === targetHandle) {
        onNotice(t('canvas.noticeSameFieldOrNode'));
        return;
      }
      const sourceIsTable = sourceHandle === TABLE_SOURCE_HANDLE;
      const targetIsTable = targetHandle === TABLE_TARGET_HANDLE;
      if (sourceIsTable !== targetIsTable) {
        onNotice(t('canvas.noticeMixedLevel'));
        return;
      }

      const fromField = sourceIsTable
        ? null
        : parseFieldHandle(sourceHandle, 'field:out:');
      const toField = targetIsTable
        ? null
        : parseFieldHandle(targetHandle, 'field:in:');
      if (!sourceIsTable && (!fromField || !toField)) {
        onNotice(t('canvas.noticeHandleUnrecognized'));
        return;
      }
      if (source === target && sourceIsTable) {
        onNotice(t('canvas.noticeSameDataset'));
        return;
      }
      if (source === target && fromField !== null && fromField === toField) {
        onNotice(t('canvas.noticeSameField'));
        return;
      }

      onConnectRequest({
        from_dataset: source,
        from_field: fromField,
        to_dataset: target,
        to_field: toField,
      });
    },
    [onConnectRequest, onNotice, t],
  );

  /**
   * R15.1 split layer ①: the dagre layout re-runs only when the graph / collapsed set / field-expanded set change
   * (these three determine node sizes and graph structure). Trace state, grouping and dragging no longer trigger dagre.
   */
  const layoutPositions = useMemo(
    () =>
      graph
        ? layoutDatasets(graph.datasets, graph.edges, collapsedIds, fieldsExpandedIds)
        : null,
    [graph, collapsedIds, fieldsExpandedIds],
  );

  /**
   * R15.1 split layer ②: build node/edge collections without trace coloring (the "baseline" visual before tracing,
   * field-for-field equivalent to the pre-refactor output with an empty chain). Dependencies deliberately exclude chain/hops —
   * clicking a field trace or changing hops no longer triggers an O(V+E) collection rebuild and setNodes/setEdges.
   */
  const { baseNodes, baseEdges } = useMemo(() => {
    if (!graph) {
      return { baseNodes: EMPTY_NODES, baseEdges: EMPTY_EDGES };
    }
    const positions = layoutPositions ?? new Map();

    const present = new Set(graph.datasets.map((dataset) => dataset.id));

    // Group mapping: member datasets are hidden at the view layer; cross-group edges aggregate onto the group node
    const datasetGroups = new Map<string, CollapsedGroup>();
    groups.forEach((group) => {
      const memberIds = group.memberIds.filter((id) => present.has(id));
      if (memberIds.length < 2) return;
      memberIds.forEach((id) => datasetGroups.set(id, group));
    });
    const hiddenIds = new Set(datasetGroups.keys());

    const positionOf = (datasetId: string) => {
      const dragged = draggedPositions.current.get(datasetId);
      if (dragged) return dragged;
      const position = positions.get(datasetId);
      return { x: position?.x ?? 0, y: position?.y ?? 0 };
    };

    // 02 §7 #32: display-only derivation — when a field is an endpoint of any AI candidate edge, the field row renders a sparkles badge.
    // No edge-building/selection logic is changed.
    const aiEndpointFields = new Map<string, Set<string>>();
    graph.edges.forEach((edge) => {
      if (edge.source !== 'ai') return;
      if (edge.from_field) {
        const names = aiEndpointFields.get(edge.from_dataset) ?? new Set<string>();
        names.add(edge.from_field);
        aiEndpointFields.set(edge.from_dataset, names);
      }
      if (edge.to_field) {
        const names = aiEndpointFields.get(edge.to_dataset) ?? new Set<string>();
        names.add(edge.to_field);
        aiEndpointFields.set(edge.to_dataset, names);
      }
    });

    const nextNodes: FlowNode[] = [];
    graph.datasets.forEach((dataset) => {
      if (hiddenIds.has(dataset.id)) return;
      const position = positionOf(dataset.id);
      const aiFields = aiEndpointFields.get(dataset.id);
      nextNodes.push({
        id: dataset.id,
        type: 'dataset',
        position,
        style: { width: NODE_WIDTH },
        data: {
          dataset,
          collapsed: collapsedIds.has(dataset.id),
          isSeed: dataset.id === seedDatasetId,
          fieldsExpanded: fieldsExpandedIds.has(dataset.id),
          connectable: canEdit,
          aiEndpointFields: aiFields ? Array.from(aiFields) : [],
          // Trace-colored fields: the baseline is always an empty list; hits are shallow-patched by split layer ③
          chainFieldNames: [],
          focusedFieldNames: [],
          onToggleCollapse,
          onToggleFields,
          onSelectField: handleSelectField,
        },
        draggable: true,
        selectable: true,
        zIndex: dataset.id === seedDatasetId ? 4 : 1,
      });
    });

    // Group nodes sit at the center of members' current bounding box and do not participate in the dagre layout (minimal implementation trade-off).
    groups.forEach((group) => {
      const memberIds = group.memberIds.filter((id) => present.has(id));
      if (memberIds.length < 2) return;
      const memberPositions = memberIds.map(positionOf);
      const centerX =
        memberPositions.reduce((sum, position) => sum + position.x, 0) /
        memberPositions.length;
      const centerY =
        memberPositions.reduce((sum, position) => sum + position.y, 0) /
        memberPositions.length;
      const draggedGroup = draggedPositions.current.get(group.id);
      nextNodes.push({
        id: group.id,
        type: 'group',
        position: draggedGroup ?? {
          x: centerX + NODE_WIDTH / 2 - 124,
          y: centerY + 70,
        },
        style: { width: 248 },
        data: {
          label: group.label,
          memberIds,
          onExpand: handleExpandGroup,
        },
        draggable: true,
        selectable: false,
        zIndex: 3,
      });
    });

    // Only render handles/edges for fields actually visible in the node; edges of fields hidden by partial folding are hidden too
    const fieldNames = new Map(
      graph.datasets.map((dataset) => [
        dataset.id,
        new Set(
          (fieldsExpandedIds.has(dataset.id)
            ? dataset.fields
            : dataset.fields.slice(0, FIELD_PREVIEW_LIMIT)
          ).map((field) => field.name),
        ),
      ]),
    );

    const nextEdges: LineageFlowEdge[] = [];
    const aggregateEdges = new Map<string, AggregateEdge>();

    const edgeData = (
      edge: LineageEdge,
      kind: EdgeKind,
      fromLabel: string,
      toLabel: string,
    ): LineageEdgeData => ({
      edge,
      kind,
      fromLabel,
      toLabel,
      canEdit,
      onSelect: () => onSelectEdge(edge),
      onEdit: canEdit ? () => onSelectEdge(edge, { edit: true }) : undefined,
      onDelete: canEdit ? () => onRequestDeleteEdge(edge) : undefined,
    });

    graph.edges.forEach((edge) => {
      if (!present.has(edge.from_dataset) || !present.has(edge.to_dataset)) {
        return;
      }

      const fromGroup = datasetGroups.get(edge.from_dataset);
      const toGroup = datasetGroups.get(edge.to_dataset);
      if (fromGroup && toGroup && fromGroup.id === toGroup.id) {
        return;
      }

      if (fromGroup || toGroup) {
        // Cross-group edge aggregation: keep one link per "group/dataset" pair; concrete edges can be edited after expanding the group
        const sourceNode = fromGroup?.id ?? edge.from_dataset;
        const targetNode = toGroup?.id ?? edge.to_dataset;
        const key = `${sourceNode}-->${targetNode}`;
        const existing = aggregateEdges.get(key);
        if (existing) {
          existing.count += 1;
        } else {
          aggregateEdges.set(key, {
            sourceNode,
            targetNode,
            sourceLabel: fromGroup
              ? fromGroup.label
              : `${edge.from_dataset}.*`,
            targetLabel: toGroup ? toGroup.label : `${edge.to_dataset}.*`,
            edge,
            count: 1,
          });
        }
        return;
      }

      const fromField = edge.from_field;
      const toField = edge.to_field;

      if (fromField === null || toField === null) {
        const visual = getEdgeVisual(edge);
        nextEdges.push({
          id: `edge-${edge.id}-table`,
          source: edge.from_dataset,
          target: edge.to_dataset,
          sourceHandle: TABLE_SOURCE_HANDLE,
          targetHandle: TABLE_TARGET_HANDLE,
          type: 'lineage',
          data: edgeData(
            edge,
            'table',
            `${edge.from_dataset}.*`,
            `${edge.to_dataset}.*`,
          ),
          ariaLabel: t('canvas.ariaTableEdge', {
            from: edge.from_dataset,
            to: edge.to_dataset,
            source: edge.source,
          }),
          style: {
            stroke: visual.color,
            strokeWidth: visual.width,
            strokeDasharray: visual.dash,
            opacity: 0.92,
          },
          animated: visual.isAi,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: visual.color,
            width: 15,
            height: 15,
          },
          zIndex: 0,
          selectable: true,
          focusable: false,
        });
        return;
      }

      if (
        collapsedIds.has(edge.from_dataset) ||
        collapsedIds.has(edge.to_dataset)
      ) {
        return;
      }
      if (
        !fieldNames.get(edge.from_dataset)?.has(fromField) ||
        !fieldNames.get(edge.to_dataset)?.has(toField)
      ) {
        return;
      }

      const visual = getEdgeVisual(edge);
      nextEdges.push({
        id: `edge-${edge.id}-field`,
        source: edge.from_dataset,
        target: edge.to_dataset,
        sourceHandle: fieldSourceHandle(fromField),
        targetHandle: fieldTargetHandle(toField),
        type: 'lineage',
        data: edgeData(
          edge,
          'field',
          `${edge.from_dataset}.${fromField}`,
          `${edge.to_dataset}.${toField}`,
        ),
        ariaLabel: t('canvas.ariaFieldEdge', {
          from: `${edge.from_dataset}.${fromField}`,
          to: `${edge.to_dataset}.${toField}`,
          source: edge.source,
        }),
        style: {
          stroke: visual.color,
          strokeWidth: visual.width,
          strokeDasharray: visual.dash,
          opacity: 0.95,
        },
        animated: visual.isAi,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: visual.color,
          width: 15,
          height: 15,
        },
        zIndex: 0,
        selectable: true,
        focusable: false,
      });
    });

    // View-derived links: same-name field matches on both ends of table-level lineage (not stored edges; not selectable/editable)
    derivedLinks.forEach((link) => {
      if (!present.has(link.from_dataset) || !present.has(link.to_dataset)) {
        return;
      }
      // Do not draw derived lines inside/cross groups: cross-group relations are already expressed by aggregate edges
      if (
        datasetGroups.has(link.from_dataset) ||
        datasetGroups.has(link.to_dataset)
      ) {
        return;
      }
      if (
        collapsedIds.has(link.from_dataset) ||
        collapsedIds.has(link.to_dataset)
      ) {
        return;
      }
      if (
        !fieldNames.get(link.from_dataset)?.has(link.from_field) ||
        !fieldNames.get(link.to_dataset)?.has(link.to_field)
      ) {
        return;
      }

      const key = derivedLinkKey(link);
      nextEdges.push({
        id: `edge-derived-${key}`,
        source: link.from_dataset,
        target: link.to_dataset,
        sourceHandle: fieldSourceHandle(link.from_field),
        targetHandle: fieldTargetHandle(link.to_field),
        type: 'lineage',
        data: {
          kind: 'field',
          derived: true,
          derivedLinkKey: key,
          fromLabel: `${link.from_dataset}.${link.from_field}`,
          toLabel: `${link.to_dataset}.${link.to_field}`,
        },
        ariaLabel: t('canvas.ariaDerivedEdge', {
          from: `${link.from_dataset}.${link.from_field}`,
          to: `${link.to_dataset}.${link.to_field}`,
        }),
        style: {
          stroke: EDGE_COLORS.derived,
          strokeWidth: 1.3,
          strokeDasharray: '2 4',
          opacity: 0.9,
        },
        animated: false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: EDGE_COLORS.derived,
          width: 13,
          height: 13,
        },
        zIndex: 0,
        selectable: false,
        focusable: false,
      });
    });

    aggregateEdges.forEach((aggregate) => {
      const visual = getEdgeVisual(aggregate.edge);
      const data: LineageEdgeData = {
        edge: aggregate.edge,
        kind: 'table',
        fromLabel: aggregate.sourceLabel,
        toLabel: aggregate.targetLabel,
        aggregateCount: aggregate.count,
      };
      nextEdges.push({
        id: `edge-agg-${encodeURIComponent(aggregate.sourceNode)}-${encodeURIComponent(aggregate.targetNode)}`,
        source: aggregate.sourceNode,
        target: aggregate.targetNode,
        sourceHandle: TABLE_SOURCE_HANDLE,
        targetHandle: TABLE_TARGET_HANDLE,
        type: 'lineage',
        data,
        ariaLabel: t('canvas.ariaAggregateEdge', {
          from: aggregate.sourceLabel,
          to: aggregate.targetLabel,
          count: aggregate.count,
        }),
        style: {
          stroke: visual.color,
          strokeWidth: 1.5,
          strokeDasharray: visual.dash ?? '5 4',
          opacity: 0.85,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: visual.color,
          width: 15,
          height: 15,
        },
        zIndex: 0,
        selectable: false,
        focusable: false,
      });
    });

    return { baseNodes: nextNodes, baseEdges: nextEdges };
  }, [
    graph,
    layoutPositions,
    derivedLinks,
    collapsedIds,
    fieldsExpandedIds,
    groups,
    seedDatasetId,
    canEdit,
    onToggleCollapse,
    onToggleFields,
    handleSelectField,
    onSelectEdge,
    onRequestDeleteEdge,
    t,
  ]);

  /**
   * R15.1 split layer ③: trace coloring — shallow-patch only the data of nodes on the hit chain
   * (chainFieldNames/focusedFieldNames); untouched nodes keep their object references,
   * so DatasetNode's memo prevents re-rendering; without trace state the baseline collection is reused directly.
   */
  const finalNodes = useMemo(() => {
    if (!chain) return baseNodes;
    const chainByDataset = new Map<
      string,
      { focused: string[]; linked: string[] }
    >();
    chain.nodes.forEach((node) => {
      const entry =
        chainByDataset.get(node.datasetId) ?? { focused: [], linked: [] };
      if (node.role === 'focus') entry.focused.push(node.fieldName);
      else entry.linked.push(node.fieldName);
      chainByDataset.set(node.datasetId, entry);
    });
    return baseNodes.map((node) => {
      if (node.type !== 'dataset') return node;
      const entry = chainByDataset.get(node.id);
      const linked = entry?.linked ?? [];
      const focused = entry?.focused ?? [];
      const data = node.data;
      if (
        sameStringList(data.chainFieldNames ?? [], linked) &&
        sameStringList(data.focusedFieldNames ?? [], focused)
      ) {
        return node;
      }
      return {
        ...node,
        data: { ...node.data, chainFieldNames: linked, focusedFieldNames: focused },
      };
    });
  }, [baseNodes, chain]);

  /**
   * R15.1 split layer ③ (edges): rewrite coloring-related fields per focusState (data.focusState/
   * style/animated/markerEnd/zIndex). Edge array objects are fully replaced when trace state activates,
   * but dagre and node rebuilding are no longer triggered.
   */
  const finalEdges = useMemo(() => {
    if (!chain) return baseEdges;
    return baseEdges.map((edge) => {
      const data = edge.data as LineageEdgeData | undefined;
      if (!data) return edge;
      return applyEdgeFocus(edge, edgeFocusStateOf(data, chain));
    });
  }, [baseEdges, chain]);

  // Sync memo output into React Flow state; when references are unchanged the effect does not fire and nothing is written
  useEffect(() => {
    setNodes(finalNodes);
    setEdges(finalEdges);
  }, [finalNodes, finalEdges, setNodes, setEdges]);

  useEffect(() => {
    if (!flowInstance || !graph || graph.datasets.length === 0) return;
    const timer = window.setTimeout(() => {
      void flowInstance.fitView({
        padding: 0.18,
        duration: 300,
        minZoom: 0.28,
        maxZoom: 0.95,
      });
    }, 100);
    return () => window.clearTimeout(timer);
    // Filtering only changes the edge set, not the viewport; seed/hop/group changes refit
  }, [flowInstance, seedDatasetId, hops, graph?.datasets.length, groups.length]);

  // R15.5: localize aria copy of React Flow's built-in controls (v12 supports ariaLabelConfig overrides)
  const ariaLabelConfig = useMemo(
    () => ({
      'controls.ariaLabel': t('canvas.ariaControls'),
      'controls.zoomIn.ariaLabel': t('canvas.ariaZoomIn'),
      'controls.zoomOut.ariaLabel': t('canvas.ariaZoomOut'),
      'controls.fitView.ariaLabel': t('canvas.ariaFitView'),
    }),
    [t],
  );

  const dismissMobileHints = useCallback(() => {
    setMobileHintsDismissed(true);
    try {
      localStorage.setItem(MOBILE_HINTS_STORAGE_KEY, '1');
    } catch {
      // When localStorage is unavailable (private mode, etc.), hide for this session only
    }
  }, []);

  // R16: edge-list data source = the current filtered graph (graph is the Workspace-filtered result),
  // including edges directly connected to the traced focus field (pinned + highlighted); local keyword filtering
  const edgeListRows = useMemo(() => {
    if (!graph) return { rows: [] as EdgeListRow[], truncated: false };
    const tableLevel = t('canvas.edgeListTableLevel');
    const rows = graph.edges.map((edge) => ({
      edge,
      fromLabel: `${edge.from_dataset}.${edge.from_field ?? tableLevel}`,
      toLabel: `${edge.to_dataset}.${edge.to_field ?? tableLevel}`,
      connectedToFocus:
        focusFields.length > 0 &&
        focusFields.some(
          (focus) =>
            (focus.datasetId === edge.from_dataset &&
              focus.fieldName === edge.from_field) ||
            (focus.datasetId === edge.to_dataset &&
              focus.fieldName === edge.to_field),
        ),
    }));
    const query = edgeListQuery.trim().toLowerCase();
    const matching = query
      ? rows.filter(
          (row) =>
            row.fromLabel.toLowerCase().includes(query) ||
            row.toLabel.toLowerCase().includes(query),
        )
      : rows;
    // sort is stable in modern JS engines: connected edges first, the rest keep their order
    const sorted = [...matching].sort(
      (a, b) => Number(b.connectedToFocus) - Number(a.connectedToFocus),
    );
    return {
      rows: sorted.slice(0, EDGE_LIST_LIMIT),
      truncated: sorted.length > EDGE_LIST_LIMIT,
    };
  }, [graph, focusFields, edgeListQuery, t]);

  const handleEdgeListSelect = useCallback(
    (edge: LineageEdge) => {
      // Same flow as clicking an edge on the canvas: clear trace state → open EdgeDetailPanel
      setFocusFields([]);
      onSelectEdge(edge);
    },
    [onSelectEdge],
  );

  const allCollapsed =
    Boolean(graph?.datasets.length) &&
    graph!.datasets.every((dataset) => collapsedIds.has(dataset.id));
  const seedName =
    graph?.datasets.find((dataset) => dataset.id === seedDatasetId)?.name ??
    seedDatasetId;
  const filteredEdgeCount = graph?.edges.length ?? 0;
  const showFilteredEmptyHint =
    Boolean(graph) && filteredEdgeCount === 0 && totalEdgeCount > 0;

  // R15.2: show a loading card while the first-screen dataset list loads; never flash the "select a dataset" empty state
  if (!graph && !loading && !error && datasetsLoading) {
    return (
      <div className="relative flex h-full min-h-[560px] items-center justify-center overflow-hidden bg-page bg-dot-grid bg-grid-24">
        <div
          className="flex items-center gap-2.5 rounded-lg border border-line bg-card px-4 py-3 shadow-float"
          role="status"
          aria-live="polite"
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
          <div className="text-[13px] font-medium text-ink">
            {t('canvas.loadingDatasets')}
          </div>
        </div>
      </div>
    );
  }

  if (!graph && !loading && !error) {
    return (
      <div className="relative flex h-full min-h-[560px] items-center justify-center overflow-hidden bg-page bg-dot-grid bg-grid-24">
        <div className="relative mx-6 max-w-sm rounded-2xl border border-dashed border-line-strong bg-card/75 px-8 py-9 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-brand-200 bg-brand-50 text-brand-600">
            <Icon name="network" size={22} />
          </div>
          <h2 className="mt-4 text-xl font-medium text-ink">
            {t('canvas.emptyTitle')}
          </h2>
          <p className="mt-2 text-[13px] leading-5 text-ink-muted">
            {t('canvas.emptyHint')}
          </p>
        </div>
      </div>
    );
  }

  const groupableCount = selectedNodeIds.length;
  const hasGroupControls = groupableCount >= 2 || groups.length > 0;

  return (
    <div className="relative h-full min-h-[560px] bg-page bg-dot-grid bg-grid-24">
      {graph && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDragStop={handleNodeDragStop}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onInit={(instance) => setFlowInstance(instance)}
          onSelectionChange={handleSelectionChange}
          onNodeClick={handleNodeClick}
          onEdgeClick={handleEdgeClick}
          onPaneClick={handlePaneClick}
          onConnect={handleConnect}
          fitView
          fitViewOptions={{ padding: 0.18, maxZoom: 0.95 }}
          minZoom={0.22}
          maxZoom={1.65}
          nodesConnectable={canEdit}
          nodesFocusable
          edgesFocusable={false}
          selectionKeyCode="Shift"
          multiSelectionKeyCode={['Meta', 'Control', 'Shift']}
          deleteKeyCode={null}
          elevateNodesOnSelect
          proOptions={{ hideAttribution: true }}
          className="lineage-flow"
          aria-label={t('canvas.ariaCanvas')}
          ariaLabelConfig={ariaLabelConfig}
        >
          <Controls
            position="bottom-left"
            showInteractive={false}
            className="lineage-controls"
            aria-label={t('canvas.ariaControls')}
          />
          <MiniMap
            position="bottom-right"
            pannable
            zoomable
            nodeColor={(node) => (node.id === seedDatasetId ? '#EA580C' : '#CBD5E1')}
            nodeStrokeColor="#FFFFFF"
            nodeBorderRadius={4}
            maskColor="rgba(248, 250, 252, 0.65)"
            className="lineage-minimap"
            ariaLabel={t('canvas.ariaMinimap')}
          />

          <Panel position="top-left" className="!m-3">
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-card p-1.5 pr-2 shadow-float">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white">
                  <Icon name="network" size={14} />
                </span>
                <div className="px-0.5">
                  <div className="max-w-[140px] truncate text-[13px] font-medium text-ink">
                    {seedName || t('canvas.subgraphFallback')}
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] tabular-nums text-ink-faint">
                    {t('canvas.subgraphStats', {
                      datasets: graph.datasets.length,
                      edges: graph.edges.length,
                    })}
                  </div>
                </div>
                <span className="mx-1 h-5 w-px bg-line" aria-hidden="true" />
                <button
                  type="button"
                  onClick={onToggleAll}
                  className="flex h-7 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-2.5 text-[12px] font-medium text-ink-soft transition-colors duration-150 hover:border-brand-400 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1"
                  title={
                    allCollapsed
                      ? t('canvas.expandAllFieldsTitle')
                      : t('canvas.collapseAllFieldsTitle')
                  }
                >
                  <Icon
                    name={allCollapsed ? 'unfold-all' : 'fold-all'}
                    size={12}
                  />
                  {allCollapsed ? t('canvas.expandAll') : t('canvas.collapseAll')}
                </button>
              </div>

              {hasGroupControls && (
                <div className="flex animate-fade-in flex-wrap items-center gap-2 rounded-lg border border-line bg-card p-1.5 pr-2 shadow-float">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-line-soft bg-subtle text-ink-muted">
                    <Icon name="group" size={14} />
                  </span>
                  {groupableCount >= 2 && (
                    <button
                      type="button"
                      onClick={handleCollapseSelected}
                      className="flex h-7 items-center gap-1.5 rounded-lg border border-brand-200 bg-brand-50 px-2.5 text-[12px] font-medium text-brand-800 transition-colors duration-150 hover:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1"
                      title={t('canvas.groupSelectedTitle')}
                    >
                      <Icon name="fold-all" size={12} />
                      {t('canvas.groupSelected', { count: groupableCount })}
                    </button>
                  )}
                  {groups.length > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        groups.forEach((group) =>
                          draggedPositions.current.delete(group.id),
                        );
                        setGroups([]);
                      }}
                      className="flex h-7 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-2.5 text-[12px] font-medium text-ink-soft transition-colors duration-150 hover:border-brand-400 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1"
                    >
                      <Icon name="unfold-all" size={12} />
                      {t('canvas.expandAllGroups', { count: groups.length })}
                    </button>
                  )}
                </div>
              )}
            </div>
          </Panel>

          {/* R15.3: empty-state hint when filtering cleared all edges but the parent graph has some */}
          {showFilteredEmptyHint && (
            <Panel position="top-center" className="!mt-3">
              <div className="flex items-center gap-2 rounded-full border border-line bg-card/90 px-3 py-1.5 text-[12px] text-ink-muted shadow-float">
                <Icon name="info" size={13} className="shrink-0 text-ink-faint" />
                {t('canvas.filteredEdgesEmpty')}
              </div>
            </Panel>
          )}

          <Panel position="bottom-center" className="!mb-2 hidden md:block">
            <div className="flex items-center gap-2.5 rounded-full border border-line bg-card/90 px-3 py-1.5 font-mono text-[11px] text-ink-muted shadow-float">
              <span>{t('canvas.hintPan')}</span>
              <span className="h-2 w-px bg-line" />
              <span>{t('canvas.hintBoxSelect')}</span>
              <span className="h-2 w-px bg-line" />
              <span>{t('canvas.hintEdgeDetails')}</span>
              <span className="h-2 w-px bg-line" />
              <span>{t('canvas.hintFieldTrace')}</span>
              {canEdit && (
                <>
                  <span className="h-2 w-px bg-line" />
                  <span>{t('canvas.hintCreateEdge')}</span>
                </>
              )}
            </div>
          </Panel>

          {/* R15.4: first-visit hint below md (hidden once read state is remembered in localStorage) */}
          {!mobileHintsDismissed && (
            <Panel position="bottom-center" className="!mb-2 md:hidden">
              <div className="flex max-w-[92vw] flex-wrap items-center gap-x-2.5 gap-y-1 rounded-lg border border-line bg-card/95 px-3 py-1.5 font-mono text-[11px] text-ink-muted shadow-float">
                <span>{t('canvas.hintPan')}</span>
                <span className="h-2 w-px bg-line" />
                <span>{t('canvas.hintBoxSelect')}</span>
                <span className="h-2 w-px bg-line" />
                <span>{t('canvas.hintEdgeDetails')}</span>
                <span className="h-2 w-px bg-line" />
                <span>{t('canvas.hintFieldTrace')}</span>
                {canEdit && (
                  <>
                    <span className="h-2 w-px bg-line" />
                    <span>{t('canvas.hintCreateEdge')}</span>
                  </>
                )}
                <span className="h-2 w-px bg-line" />
                <span>{t('canvas.hintMobileGroup')}</span>
                <button
                  type="button"
                  onClick={dismissMobileHints}
                  aria-label={t('canvas.mobileHintsDismiss')}
                  className="ml-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line bg-card text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60"
                >
                  <Icon name="close" size={10} />
                </button>
              </div>
            </Panel>
          )}

          {/* R16: secondary edge-list entry (collapsed by default; sits directly above the bottom Controls) */}
          {(filteredEdgeCount > 0 || totalEdgeCount > 0) && (
            <Panel
              position="bottom-left"
              className={EDGE_LIST_PANEL_CLASS}
            >
              {edgeListOpen ? (
                <div
                  id="canvas-edge-list"
                  className={`flex flex-col overflow-hidden rounded-lg border border-line bg-card shadow-float ${EDGE_LIST_WIDTH_CLASS}`}
                >
                  <div className="flex items-center gap-2 border-b border-line-soft px-2.5 py-2">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                      <Icon name="link" size={12} />
                    </span>
                    <span className="text-[12px] font-medium text-ink">
                      {t('canvas.edgeListTitle')}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-right font-mono text-[11px] tabular-nums text-ink-faint">
                      {edgeListRows.rows.length}
                      {edgeListRows.truncated ? '+' : ''}
                    </span>
                    <button
                      type="button"
                      onClick={() => setEdgeListOpen(false)}
                      aria-label={t('canvas.edgeListCollapse')}
                      title={t('canvas.edgeListCollapse')}
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60"
                    >
                      <Icon name="chevron-down" size={12} />
                    </button>
                  </div>
                  <div className="border-b border-line-soft px-2.5 py-1.5">
                    <label htmlFor="canvas-edge-list-filter" className="sr-only">
                      {t('canvas.edgeListFilterLabel')}
                    </label>
                    <input
                      id="canvas-edge-list-filter"
                      type="search"
                      value={edgeListQuery}
                      onChange={(event) => setEdgeListQuery(event.target.value)}
                      placeholder={t('canvas.edgeListFilterPlaceholder')}
                      autoComplete="off"
                      spellCheck={false}
                      className="field-input h-7 rounded-md text-[12px]"
                    />
                  </div>
                  <div className="max-h-[264px] overflow-y-auto py-1">
                    {edgeListRows.rows.map((row) => (
                      <button
                        key={row.edge.id}
                        type="button"
                        onClick={() => handleEdgeListSelect(row.edge)}
                        aria-label={t('canvas.edgeListRowLabel', {
                          from: row.fromLabel,
                          to: row.toLabel,
                        })}
                        title={t('canvas.edgeListRowLabel', {
                          from: row.fromLabel,
                          to: row.toLabel,
                        })}
                        className={`flex h-8 w-full items-center gap-2 px-2.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-inset focus-visible:ring-2 focus-visible:ring-brand-600/60 hover:bg-subtle ${
                          row.connectedToFocus
                            ? 'bg-brand-50/70 ring-1 ring-inset ring-brand-200/80'
                            : ''
                        }`}
                      >
                        <span className="flex min-w-0 flex-1 items-center gap-1 font-mono text-[11px] text-ink-soft">
                          <span className="min-w-0 truncate" title={row.fromLabel}>
                            {row.fromLabel}
                          </span>
                          <Icon
                            name="arrow-right"
                            size={10}
                            className="shrink-0 text-ink-faint"
                          />
                          <span className="min-w-0 truncate" title={row.toLabel}>
                            {row.toLabel}
                          </span>
                        </span>
                        <SourceBadge
                          source={row.edge.source}
                          withDescription={false}
                          className="shrink-0"
                        />
                        <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-faint">
                          {formatConfidence(row.edge.confidence)}
                        </span>
                      </button>
                    ))}
                    {edgeListRows.rows.length === 0 && (
                      <p className="px-2.5 py-3 text-center text-[11px] text-ink-faint">
                        {t('canvas.edgeListEmpty')}
                      </p>
                    )}
                  </div>
                  {edgeListRows.truncated && (
                    <p className="border-t border-line-soft px-2.5 py-1.5 font-mono text-[11px] text-ink-faint">
                      {t('canvas.edgeListLimit', { limit: EDGE_LIST_LIMIT })}
                    </p>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setEdgeListOpen(true)}
                  aria-expanded={edgeListOpen}
                  aria-controls="canvas-edge-list"
                  aria-label={t('canvas.edgeListOpen')}
                  title={t('canvas.edgeListOpen')}
                  className="flex h-8 items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 text-[12px] font-medium text-ink-soft shadow-float transition-colors duration-150 hover:border-brand-400 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1"
                >
                  <Icon name="link" size={12} />
                  {t('canvas.edgeListTitle')}
                </button>
              )}
            </Panel>
          )}
        </ReactFlow>
      )}

      {loading && (
        <div
          className="absolute inset-0 z-20 flex items-center justify-center bg-page/60"
          role="status"
          aria-live="polite"
        >
          <div className="flex items-center gap-2.5 rounded-lg border border-line bg-card px-4 py-3 shadow-float">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
            <div>
              <div className="text-[13px] font-medium text-ink">{t('canvas.loadingTitle')}</div>
              <div className="mt-0.5 font-mono text-[11px] text-ink-faint">
                {t('canvas.loadingDetail', { seed: seedDatasetId ?? '', hops })}
              </div>
            </div>
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-page/60 p-5">
          <div
            className="w-full max-w-sm rounded-xl border border-line bg-card p-5 shadow-float"
            role="alert"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-danger-soft text-danger-deep">
                <Icon name="warning" size={17} />
              </span>
              <div className="min-w-0">
                <h2 className="text-[13px] font-semibold text-ink">
                  {t('canvas.errorTitle')}
                </h2>
                <p className="mt-1.5 break-words text-[12px] leading-5 text-ink-muted">
                  {error}
                </p>
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-3 inline-flex h-7 items-center gap-1.5 rounded-lg bg-brand-700 px-2.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-brand-800 active:bg-brand-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1"
                >
                  <Icon name="refresh" size={12} />
                  {t('canvas.reload')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
