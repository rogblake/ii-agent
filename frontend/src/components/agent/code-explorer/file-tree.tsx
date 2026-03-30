import { useCallback } from 'react'
import { ChevronRightIcon } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import {
    useAppDispatch,
    useAppSelector,
    selectExpandedDirs,
    selectActiveFilePath,
    toggleDir
} from '@/state'
import type { FileTreeNode as FileTreeNodeType } from '@/state/slice/file-explorer'
import { FileIconComponent } from './file-icon'

interface FileTreeProps {
    tree: FileTreeNodeType
    onFileSelect: (path: string) => void
    depth?: number
}

export function FileTree({ tree, onFileSelect, depth = 0 }: FileTreeProps) {
    if (!tree.children) return null

    return (
        <div className={depth === 0 ? 'py-1' : ''}>
            {tree.children.map((node) => (
                <FileTreeItem
                    key={node.path}
                    node={node}
                    depth={depth}
                    onFileSelect={onFileSelect}
                />
            ))}
        </div>
    )
}

interface FileTreeItemProps {
    node: FileTreeNodeType
    depth: number
    onFileSelect: (path: string) => void
}

function FileTreeItem({ node, depth, onFileSelect }: FileTreeItemProps) {
    const dispatch = useAppDispatch()
    const expandedDirs = useAppSelector(selectExpandedDirs)
    const activeFilePath = useAppSelector(selectActiveFilePath)

    const isDir = node.type === 'directory'
    const isExpanded = expandedDirs.includes(node.path)
    const isActive = activeFilePath === node.path

    const handleClick = useCallback(() => {
        if (isDir) {
            dispatch(toggleDir(node.path))
        } else {
            onFileSelect(node.path)
        }
    }, [isDir, node.path, dispatch, onFileSelect])

    return (
        <div>
            <button
                onClick={handleClick}
                className={cn(
                    'flex w-full cursor-pointer items-center gap-1.5 px-2 py-[3px] text-left text-[13px] leading-[22px] transition-colors',
                    isActive && !isDir
                        ? 'bg-firefly/10 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue'
                        : isDir
                          ? 'text-muted-foreground hover:bg-accent/60 hover:text-foreground dark:hover:bg-white/5 dark:hover:text-white/90'
                          : 'text-muted-foreground hover:bg-sky-blue/20 hover:text-firefly dark:hover:bg-sky-blue/15 dark:hover:text-sky-blue'
                )}
                style={{ paddingLeft: `${depth * 16 + 8}px` }}
            >
                {isDir && (
                    <motion.span
                        animate={{ rotate: isExpanded ? 90 : 0 }}
                        transition={{ duration: 0.15 }}
                        className="shrink-0"
                    >
                        <ChevronRightIcon
                            size={14}
                            className="text-muted-foreground"
                        />
                    </motion.span>
                )}
                {!isDir && <span className="w-[14px] shrink-0" />}
                <FileIconComponent
                    name={node.name}
                    isDirectory={isDir}
                    isExpanded={isExpanded}
                />
                <span className="truncate select-none">{node.name}</span>
            </button>

            <AnimatePresence initial={false}>
                {isDir && isExpanded && node.children && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="overflow-hidden"
                    >
                        {node.children.map((child) => (
                            <FileTreeItem
                                key={child.path}
                                node={child}
                                depth={depth + 1}
                                onFileSelect={onFileSelect}
                            />
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}
