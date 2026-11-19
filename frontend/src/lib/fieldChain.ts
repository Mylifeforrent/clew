import type { LineageGraph } from '../types';

/**
 * View-layer derived "same-name field match" links.
 *
 * Not stored lineage entities: derived from table-level lineage (from_field/to_field
 * are null) by matching same-named fields on both datasets, used only for canvas
 * display and upstream/downstream trace demos; not selectable, not editable.
 */
export interface DerivedFieldLink {
  from_dataset: string;
  from_field: string;
  to_dataset: string;
  to_field: string;
}

export interface FieldChainNode {
  datasetId: string;
  fieldName: string;
  role: 'focus' | 'linked';
}

/** Upstream/downstream trace chain hit after clicking a field (undirected BFS along field-level connections). */
export interface FieldChain {
  /** IDs of stored field-level edges that were hit */
  edgeIds: Set<number>;
  /** Keys of derived same-name field links that were hit (see derivedLinkKey) */
  linkKeys: Set<string>;
  nodes: FieldChainNode[];
}

type ChainConnection =
  | { kind: 'edge'; key: number; other: string }
  | { kind: 'link'; key: string; other: string };

export function derivedLinkKey(link: DerivedFieldLink): string {
  return `${link.from_dataset}::${link.from_field}::${link.to_dataset}::${link.to_field}`;
}

/**
 * Derive same-name field match links from table-level lineage: field names shared by
 * both datasets that are not already occupied by any explicit field-level edge between
 * this pair of datasets (when an explicit mapping exists it wins, avoiding contradictions
 * between derived links and manually/AI-confirmed field mappings).
 */
export function deriveFieldMatches(graph: LineageGraph): DerivedFieldLink[] {
  const fieldsByDataset = new Map<string, Set<string>>();
  graph.datasets.forEach((dataset) => {
    fieldsByDataset.set(
      dataset.id,
      new Set(dataset.fields.map((field) => field.name)),
    );
  });

  const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);
  const explicitEndpointFields = new Map<string, Set<string>>();
  graph.edges.forEach((edge) => {
    if (edge.from_field === null || edge.to_field === null) return;
    const key = pairKey(edge.from_dataset, edge.to_dataset);
    const names = explicitEndpointFields.get(key) ?? new Set<string>();
    names.add(edge.from_field);
    names.add(edge.to_field);
    explicitEndpointFields.set(key, names);
  });

  const derived: DerivedFieldLink[] = [];
  const seen = new Set<string>();
  graph.edges.forEach((edge) => {
    // Expand table-level lineage only: an explicit field-level edge represents just one field mapping and cannot imply the others
    if (edge.from_field !== null || edge.to_field !== null) return;
    if (edge.from_dataset === edge.to_dataset) return;
    const fromFields = fieldsByDataset.get(edge.from_dataset);
    const toFields = fieldsByDataset.get(edge.to_dataset);
    if (!fromFields || !toFields) return;
    const occupied = explicitEndpointFields.get(
      pairKey(edge.from_dataset, edge.to_dataset),
    );

    fromFields.forEach((fieldName) => {
      if (!toFields.has(fieldName)) return;
      if (occupied?.has(fieldName)) return;
      const link: DerivedFieldLink = {
        from_dataset: edge.from_dataset,
        from_field: fieldName,
        to_dataset: edge.to_dataset,
        to_field: fieldName,
      };
      const key = derivedLinkKey(link);
      if (seen.has(key)) return;
      seen.add(key);
      derived.push(link);
    });
  });
  return derived;
}

/**
 * Starting from one or more clicked/declared fields, run an undirected BFS along
 * "stored field-level edges + derived same-name field links" to collect the whole
 * upstream/downstream chain; returns null when the starting fields have no field-level
 * connections at all (the canvas then does no highlighting or dimming).
 */
export function computeFieldChain(
  graph: LineageGraph,
  derivedLinks: DerivedFieldLink[],
  focus: Array<{ datasetId: string; fieldName: string }>,
): FieldChain | null {
  if (focus.length === 0) return null;
  const nodeKey = (datasetId: string, fieldName: string) =>
    `${datasetId}::${fieldName}`;
  const nodeInfo = new Map<string, { datasetId: string; fieldName: string }>();
  const adjacency = new Map<string, ChainConnection[]>();

  const connect = (
    aDataset: string,
    aField: string,
    bDataset: string,
    bField: string,
    connection: ChainConnection,
  ) => {
    const a = nodeKey(aDataset, aField);
    const b = nodeKey(bDataset, bField);
    nodeInfo.set(a, { datasetId: aDataset, fieldName: aField });
    nodeInfo.set(b, { datasetId: bDataset, fieldName: bField });
    const list = adjacency.get(a) ?? [];
    list.push({ ...connection, other: b });
    adjacency.set(a, list);
  };

  graph.edges.forEach((edge) => {
    if (edge.from_field === null || edge.to_field === null) return;
    connect(
      edge.from_dataset,
      edge.from_field,
      edge.to_dataset,
      edge.to_field,
      { kind: 'edge', key: edge.id, other: '' },
    );
    connect(
      edge.to_dataset,
      edge.to_field,
      edge.from_dataset,
      edge.from_field,
      { kind: 'edge', key: edge.id, other: '' },
    );
  });
  derivedLinks.forEach((link) => {
    const key = derivedLinkKey(link);
    connect(link.from_dataset, link.from_field, link.to_dataset, link.to_field, {
      kind: 'link',
      key,
      other: '',
    });
    connect(link.to_dataset, link.to_field, link.from_dataset, link.from_field, {
      kind: 'link',
      key,
      other: '',
    });
  });

  const focusKeys = focus.map((item) => nodeKey(item.datasetId, item.fieldName));
  const visited = new Set<string>(focusKeys);
  const edgeIds = new Set<number>();
  const linkKeys = new Set<string>();
  const queue = [...focusKeys];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    (adjacency.get(current) ?? []).forEach((connection) => {
      if (connection.kind === 'edge') edgeIds.add(connection.key);
      else linkKeys.add(connection.key);
      if (!visited.has(connection.other)) {
        visited.add(connection.other);
        queue.push(connection.other);
      }
    });
  }

  if (edgeIds.size === 0 && linkKeys.size === 0) return null;

  const focusKeySet = new Set(focusKeys);
  const nodes: FieldChainNode[] = [];
  visited.forEach((key) => {
    const info = nodeInfo.get(key);
    if (!info) return;
    nodes.push({
      ...info,
      role: focusKeySet.has(key) ? 'focus' : 'linked',
    });
  });
  return { edgeIds, linkKeys, nodes };
}
