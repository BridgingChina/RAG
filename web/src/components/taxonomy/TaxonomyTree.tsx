import { useState } from "react"
import { ChevronRight, ChevronDown, Plus, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { TaxonomyTreeItem } from "@/lib/types"

interface TaxonomyTreeProps {
  items: TaxonomyTreeItem[]
  selectedPath?: { lvl1: string; lvl2?: string; lvl3?: string }
  onSelect: (path: { lvl1: string; lvl2?: string; lvl3?: string }) => void
  onAddNode: (parent: { lvl1: string; lvl2?: string }) => void
  onDeleteNode: (nodeId: number, nodeLabel: string) => void
}

interface TreeNodeProps {
  item: TaxonomyTreeItem
  level: number
  parentPath?: { lvl1: string; lvl2?: string }
  selectedPath?: { lvl1: string; lvl2?: string; lvl3?: string }
  onSelect: (path: { lvl1: string; lvl2?: string; lvl3?: string }) => void
  onAddNode: (parent: { lvl1: string; lvl2?: string }) => void
  onDeleteNode: (nodeId: number, nodeLabel: string) => void
}

function TreeNode({
  item,
  level,
  parentPath,
  selectedPath,
  onSelect,
  onAddNode,
  onDeleteNode,
}: TreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasChildren = item.children && item.children.length > 0

  // Build current path based on level
  const currentPath =
    level === 1
      ? { lvl1: item.label }
      : level === 2 && parentPath
        ? { lvl1: parentPath.lvl1, lvl2: item.label }
        : level === 3 && parentPath
          ? { lvl1: parentPath.lvl1, lvl2: parentPath.lvl2, lvl3: item.label }
          : { lvl1: item.label }

  // Check if this node is selected
  const isSelected =
    selectedPath &&
    currentPath.lvl1 === selectedPath.lvl1 &&
    currentPath.lvl2 === selectedPath.lvl2 &&
    currentPath.lvl3 === selectedPath.lvl3

  // Padding based on level
  const paddingLeft = level * 16

  return (
    <div>
      <div
        className={`
          group flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer
          hover:bg-accent transition-colors
          ${isSelected ? "bg-accent" : ""}
        `}
        style={{ paddingLeft: `${paddingLeft}px` }}
        onClick={() => onSelect(currentPath)}
      >
        {/* Expand/collapse toggle */}
        <div className="flex-shrink-0">
          {hasChildren ? (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setIsExpanded(!isExpanded)
              }}
              className="p-0.5 hover:bg-accent-foreground/10 rounded"
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
          ) : (
            <div className="w-5" />
          )}
        </div>

        {/* Label */}
        <span className="flex-1 text-sm">{item.label}</span>

        {/* Chunk count badge */}
        <Badge variant="secondary" className="text-xs">
          {item.chunk_count}
        </Badge>

        {/* Action buttons (visible on hover) */}
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Add child button (only for lvl1 and lvl2) */}
          {level < 3 && (
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              onClick={(e) => {
                e.stopPropagation()
                onAddNode(currentPath as { lvl1: string; lvl2?: string })
              }}
              title="添加子分类"
            >
              <Plus className="h-3 w-3" />
            </Button>
          )}

          {/* Delete button */}
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-destructive hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation()
              onDeleteNode(item.node_id, item.label)
            }}
            title="删除分类"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Render children */}
      {hasChildren && isExpanded && (
        <div>
          {item.children.map((child) => {
            const childKey =
              level === 1
                ? `${currentPath.lvl1}/${child.label}`
                : `${currentPath.lvl1}/${currentPath.lvl2}/${child.label}`
            return (
              <TreeNode
                key={childKey}
                item={child}
                level={level + 1}
                parentPath={currentPath as { lvl1: string; lvl2?: string }}
                selectedPath={selectedPath}
                onSelect={onSelect}
                onAddNode={onAddNode}
                onDeleteNode={onDeleteNode}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

export function TaxonomyTree({
  items,
  selectedPath,
  onSelect,
  onAddNode,
  onDeleteNode,
}: TaxonomyTreeProps) {
  return (
    <div className="space-y-1">
      {items.map((item) => (
        <TreeNode
          key={`root/${item.label}`}
          item={item}
          level={1}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onAddNode={onAddNode}
          onDeleteNode={onDeleteNode}
        />
      ))}
    </div>
  )
}
