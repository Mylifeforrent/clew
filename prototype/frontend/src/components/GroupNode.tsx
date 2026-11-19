import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import {
  TABLE_SOURCE_HANDLE,
  TABLE_TARGET_HANDLE,
} from '../lib/handles';
import { Icon } from './Icon';

/**
 * "Collapse into group" placeholder node (minimal M3 frontend implementation).
 *
 * Trade-offs: dagre compound (subgraph) layout is not introduced and the backend
 * subgraph contract is unchanged; the group node merely hides the multi-selected
 * members at the **view layer** and sits at the center of the members' bounding box.
 * - Field-level/table-level edges among members cancel each other out inside the group;
 * - Cross-group edges aggregate into one group-level link pointing at this node's table handles;
 * - Clicking the node or the "expand" button dissolves the group (no backend write).
 */
export interface GroupNodeData extends Record<string, unknown> {
  label: string;
  memberIds: string[];
  onExpand: (groupId: string) => void;
}

export type GroupFlowNode = Node<GroupNodeData, 'group'>;

export function GroupNode({ id, data }: NodeProps) {
  const nodeData = data as unknown as GroupNodeData;
  const { label, memberIds, onExpand } = nodeData;
  const count = memberIds.length;

  return (
    <article
      className="group relative w-[248px] rounded-xl border border-dashed border-blue-600/65 bg-blue-50/85 p-3 shadow-node transition-shadow duration-150 hover:shadow-card"
      aria-label={`Collapsed group ${label}, containing ${count} datasets, click to expand`}
    >
      <Handle
        type="target"
        position={Position.Left}
        id={TABLE_TARGET_HANDLE}
        className="table-handle"
        style={{ top: 30 }}
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Right}
        id={TABLE_SOURCE_HANDLE}
        className="table-handle"
        style={{ top: 30 }}
        isConnectable={false}
      />
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onExpand(id);
        }}
        className="nodrag nopan block w-full rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-card"
        title="Expand this group"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-blue-200 bg-card text-blue-700">
            <Icon name="group" size={14} />
          </span>
          <span className="rounded-full border border-blue-200 bg-card px-1.5 py-px font-mono text-[11px] text-blue-800">
            {count} datasets
          </span>
        </div>
        <h3 className="mt-2 truncate text-[13px] font-medium text-ink">
          {label}
        </h3>
        <div className="mt-1 flex items-center gap-1.5 font-mono text-[11px] text-blue-700">
          <Icon name="unfold-all" size={10} />
          Click to expand
        </div>
      </button>
    </article>
  );
}
