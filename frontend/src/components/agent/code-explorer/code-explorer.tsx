import { useCallback } from 'react'
import { useParams } from 'react-router'
import {
    FolderTreeIcon,
    RefreshCwIcon,
    XIcon,
    CodeIcon
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
    useAppDispatch,
    useAppSelector,
    selectFileTree,
    selectOpenFiles,
    selectActiveFilePath,
    selectActiveFile,
    selectIsTreeLoading,
    selectIsFileLoading,
    selectTreeError,
    selectContentCache,
    setExplorerActiveFile,
    openCachedFile,
    closeFile,
    setFileLoading
} from '@/state'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { FileTree } from './file-tree'
import { CodeViewer } from './code-viewer'
import { FileIconComponent } from './file-icon'
import { useFileTreeSync } from './use-file-tree-sync'

interface CodeExplorerProps {
    className?: string
}

const FILE_SKELETON_WIDTHS = [
    'w-24',
    'w-5/6',
    'w-4/6',
    'w-11/12',
    'w-7/12',
    'w-10/12',
    'w-3/6',
    'w-9/12',
    'w-4/12',
    'w-8/12'
]

const TREE_SKELETON_ROWS = [
    { indent: 0, width: 'w-16' },
    { indent: 1, width: 'w-28' },
    { indent: 2, width: 'w-24' },
    { indent: 1, width: 'w-32' },
    { indent: 0, width: 'w-20' },
    { indent: 1, width: 'w-24' },
    { indent: 1, width: 'w-30' },
    { indent: 2, width: 'w-20' }
]

function TreeLoadingSkeleton() {
    return (
        <div className="px-2 py-3">
            <div className="flex flex-col gap-2">
                {TREE_SKELETON_ROWS.map((row, index) => (
                    <div
                        key={index}
                        className="flex items-center gap-2"
                        style={{ paddingLeft: `${row.indent * 16}px` }}
                    >
                        <Skeleton className="h-3 w-3 rounded-sm !bg-black/10 dark:!bg-white/10" />
                        <Skeleton
                            className={cn(
                                'h-3 rounded-sm !bg-black/10 dark:!bg-white/10',
                                row.width
                            )}
                        />
                    </div>
                ))}
            </div>
        </div>
    )
}

function FileLoadingSkeleton() {
    return (
        <div className="h-full overflow-auto bg-background p-4">
            <div className="mx-auto flex max-w-5xl flex-col gap-3">
                {FILE_SKELETON_WIDTHS.map((width, index) => (
                    <div key={index} className="flex items-center gap-4">
                        <Skeleton className="h-3 w-8 shrink-0 !bg-black/10 dark:!bg-white/10" />
                        <Skeleton
                            className={cn(
                                'h-3 rounded-sm !bg-black/10 dark:!bg-white/10',
                                width
                            )}
                        />
                    </div>
                ))}
            </div>
        </div>
    )
}

export function CodeExplorer({ className }: CodeExplorerProps) {
    const { sessionId } = useParams()
    const dispatch = useAppDispatch()
    const { sendMessage, isSessionReady } = useSocketIOContext()

    const tree = useAppSelector(selectFileTree)
    const openFiles = useAppSelector(selectOpenFiles)
    const activeFilePath = useAppSelector(selectActiveFilePath)
    const activeFile = useAppSelector(selectActiveFile)
    const isTreeLoading = useAppSelector(selectIsTreeLoading)
    const isFileLoading = useAppSelector(selectIsFileLoading)
    const treeError = useAppSelector(selectTreeError)
    const contentCache = useAppSelector(selectContentCache)

    const { requestTreeRefresh } = useFileTreeSync(sessionId)

    const handleFileSelect = useCallback(
        (path: string) => {
            if (!isSessionReady) {
                return
            }
            // If already open, just activate
            const alreadyOpen = openFiles.find((f) => f.path === path)
            if (alreadyOpen) {
                dispatch(setExplorerActiveFile(path))
                return
            }
            // Check the content cache first — instant open
            if (contentCache[path]) {
                dispatch(openCachedFile(path))
                return
            }
            // Cache miss — fetch from backend
            dispatch(setFileLoading(true))
            const sent = sendMessage({
                type: 'file_content',
                content: { path }
            })
            if (!sent) {
                dispatch(setFileLoading(false))
            }
        },
        [openFiles, contentCache, dispatch, isSessionReady, sendMessage]
    )

    const handleTabClose = useCallback(
        (e: React.MouseEvent, path: string) => {
            e.stopPropagation()
            dispatch(closeFile(path))
        },
        [dispatch]
    )

    return (
        <div
            className={cn(
                'flex h-full bg-background text-foreground dark:bg-black/10',
                className
            )}
        >
            {/* File tree sidebar */}
            <div className="flex w-[260px] shrink-0 flex-col border-r border-border bg-muted/50 dark:border-white/10 dark:bg-charcoal/40">
                {/* Sidebar header */}
                <div className="flex items-center justify-between border-b border-border px-3 py-2.5 dark:border-white/10">
                    <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        <FolderTreeIcon
                            size={14}
                            className="text-firefly dark:text-sky-blue"
                        />
                        <span>Explorer</span>
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:bg-accent hover:text-foreground dark:hover:bg-white/10 dark:hover:text-white"
                        onClick={requestTreeRefresh}
                        disabled={isTreeLoading || !isSessionReady}
                    >
                        <RefreshCwIcon
                            size={13}
                            className={isTreeLoading ? 'animate-spin' : ''}
                        />
                    </Button>
                </div>

                {/* File tree */}
                <div className="flex-1 min-h-0 overflow-y-auto with-scrollbar">
                    {isTreeLoading && !tree && (
                        <TreeLoadingSkeleton />
                    )}
                    {treeError && !tree && (
                        <div className="px-3 py-6 text-center">
                            <p className="text-xs text-red mb-2">{treeError}</p>
                            <Button
                                variant="outline"
                                size="sm"
                                className="text-xs"
                                onClick={requestTreeRefresh}
                            >
                                Retry
                            </Button>
                        </div>
                    )}
                    {tree && (
                        <FileTree tree={tree} onFileSelect={handleFileSelect} />
                    )}
                </div>
            </div>

            {/* Main content area */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* File tabs */}
                {openFiles.length > 0 && (
                    <div className="flex items-center overflow-x-auto border-b border-border bg-muted/40 no-scrollbar dark:border-white/10 dark:bg-black/10">
                        {openFiles.map((file) => {
                            const fileName =
                                file.path.split('/').pop() || file.path
                            const isActive = file.path === activeFilePath
                            return (
                                <button
                                    key={file.path}
                                    onClick={() =>
                                        dispatch(
                                            setExplorerActiveFile(file.path)
                                        )
                                    }
                                    className={cn(
                                        'flex shrink-0 cursor-pointer items-center gap-1.5 border-r border-border px-3 py-1.5 text-[13px] transition-colors dark:border-white/10',
                                        isActive
                                            ? 'border-b-2 border-b-firefly bg-firefly/10 text-firefly dark:border-b-sky-blue dark:bg-white/5 dark:text-sky-blue'
                                            : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground dark:hover:bg-white/5 dark:hover:text-white/80'
                                    )}
                                >
                                    <FileIconComponent
                                        name={fileName}
                                        isDirectory={false}
                                        className="!w-3.5 !h-3.5"
                                    />
                                    <span className="truncate max-w-[120px]">
                                        {fileName}
                                    </span>
                                    <span
                                        onClick={(e) =>
                                            handleTabClose(e, file.path)
                                        }
                                        className="ml-1 rounded p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground dark:hover:bg-white/10 dark:hover:text-white"
                                    >
                                        <XIcon size={12} />
                                    </span>
                                </button>
                            )
                        })}
                    </div>
                )}

                {/* Code viewer or empty state */}
                <div className="flex-1 overflow-hidden">
                    {isFileLoading && (
                        <FileLoadingSkeleton />
                    )}
                    {!isFileLoading && activeFile && (
                        <CodeViewer file={activeFile} sessionId={sessionId} />
                    )}
                    {!isFileLoading && !activeFile && (
                        <div className="flex h-full flex-col items-center justify-center gap-4 text-muted-foreground">
                            <div className="relative">
                                <div className="absolute inset-0 bg-sky-blue/10 rounded-full blur-xl" />
                                <div className="relative rounded-full border border-border bg-muted p-4 dark:border-white/10 dark:bg-firefly/50">
                                    <CodeIcon
                                        size={28}
                                        className="text-firefly dark:text-sky-blue"
                                    />
                                </div>
                            </div>
                            <div className="text-center">
                                <p className="mb-1 text-sm font-medium text-foreground">
                                    No file selected
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    Select a file from the explorer to view its
                                    contents
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
