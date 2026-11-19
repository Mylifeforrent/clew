import type { LineageEdge } from '../types';

/**
 * Entity naming rules for annotations / change_log (consistent with the backend):
 * - Field: <dataset_id>.<field_name>
 * - Edge: <from_dataset>.<from_field | *>--><to_dataset>.<to_field | *>
 */
export function fieldEntityKey(datasetId: string, fieldName: string): string {
  return `${datasetId}.${fieldName}`;
}

export function edgeEntityKey(edge: LineageEdge): string {
  const from = `${edge.from_dataset}.${edge.from_field ?? '*'}`;
  const to = `${edge.to_dataset}.${edge.to_field ?? '*'}`;
  return `${from}-->${to}`;
}
