import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import {
  TABLE_SOURCE_HANDLE,
  TABLE_TARGET_HANDLE,
} from '../lib/handles';
import { Icon } from './Icon';
import { useI18n } from '../i18n';

/**
 * "Collapse into group" placeholder node (minimal M3 frontend implementation).
 *
 * Trade-offs: dagre's compound (subgraph) layout is not used and the backend subgraph
 * contract is unchanged; the group node simply hides the selected members at the **view
 * layer** and sits at the center of their bounding box.
 * - Members' original field-level/table-level edges cancel out inside the group;
 * - Cross-group edges are aggregated into one group-level link pointing at this node's table handle;
 * - Clicking the node or the "expand" button dissolves the group (nothing is written to the backend).
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
  const { t } = useI18n();
  const count = memberIds.length;

  return (
    <article
      className="group relative w-[248px] rounded-xl border border-dashed border-brand-600/65 bg-brand-50/85 p-3 shadow-node transition-shadow duration-150 hover:shadow-card"
      aria-label={t('groupNode.aria', { label, count })}
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
        className="nodrag nopan block w-full rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-card"
        title={t('groupNode.expandTitle')}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-brand-200 bg-card text-brand-700">
            <Icon name="group" size={14} />
          </span>
          <span className="rounded-full border border-brand-200 bg-card px-1.5 py-px font-mono text-[11px] text-brand-800">
            {t('groupNode.datasetCount', { count })}
          </span>
        </div>
        <h3 className="mt-2 truncate text-[13px] font-medium text-ink">
          {label}
        </h3>
        <div className="mt-1 flex items-center gap-1.5 font-mono text-[11px] text-brand-700">
          <Icon name="unfold-all" size={10} />
          {t('groupNode.clickExpand')}
        </div>
      </button>
    </article>
  );
}
