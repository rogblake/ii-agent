import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export interface FileTreeNode {
    name: string
    path: string
    type: 'file' | 'directory'
    children?: FileTreeNode[]
    size?: number
}

export interface OpenTextFile {
    kind: 'text'
    path: string
    content: string
    language: string
}

export interface OpenSvgFile {
    kind: 'svg'
    path: string
    content: string
    language: string
    mimeType: string
}

export interface OpenImageFile {
    kind: 'image'
    path: string
    mimeType: string
    revision: number
}

export interface OpenBinaryFile {
    kind: 'binary'
    path: string
    mimeType?: string
    message: string
    tooBig: boolean
}

export type OpenFile =
    | OpenTextFile
    | OpenSvgFile
    | OpenImageFile
    | OpenBinaryFile

export interface CachedContent {
    content: string
    language: string
}

interface FileContentPayload {
    path: string
    content?: string
    language?: string
    fileKind?: 'text' | 'image' | 'binary'
    mimeType?: string
    message?: string
    tooBig?: boolean
}

interface FileExplorerState {
    tree: FileTreeNode | null
    rootPath: string | null
    contentCache: Record<string, CachedContent>
    openFiles: OpenFile[]
    activeFilePath: string | null
    expandedDirs: string[]
    isTreeLoading: boolean
    isFileLoading: boolean
    treeError: string | null
}

const SVG_MIME_TYPE = 'image/svg+xml'

function isSvgPath(path: string): boolean {
    return path.toLowerCase().endsWith('.svg')
}

function buildTextLikeFile(path: string, content: string, language: string): OpenTextFile | OpenSvgFile {
    if (isSvgPath(path)) {
        return {
            kind: 'svg',
            path,
            content,
            language: language || 'xml',
            mimeType: SVG_MIME_TYPE
        }
    }

    return {
        kind: 'text',
        path,
        content,
        language: language || 'plaintext'
    }
}

function buildOpenFile(payload: FileContentPayload): OpenFile {
    const {
        path,
        content = '',
        language = 'plaintext',
        fileKind = 'text',
        mimeType,
        message,
        tooBig = false
    } = payload

    if (fileKind === 'image') {
        return {
            kind: 'image',
            path,
            mimeType: mimeType || 'application/octet-stream',
            revision: 0
        }
    }

    if (fileKind === 'binary') {
        return {
            kind: 'binary',
            path,
            mimeType,
            message:
                message ||
                'Binary preview is not supported here. Open VS Code to view.',
            tooBig
        }
    }

    return buildTextLikeFile(path, content, language)
}

const initialState: FileExplorerState = {
    tree: null,
    rootPath: null,
    contentCache: {},
    openFiles: [],
    activeFilePath: null,
    expandedDirs: [],
    isTreeLoading: false,
    isFileLoading: false,
    treeError: null
}

const fileExplorerSlice = createSlice({
    name: 'fileExplorer',
    initialState,
    reducers: {
        setFileTree: (
            state,
            action: PayloadAction<{
                tree: FileTreeNode | null
                rootPath?: string
                contents?: Record<string, CachedContent>
            }>
        ) => {
            state.tree = action.payload.tree
            if (action.payload.rootPath) {
                state.rootPath = action.payload.rootPath
            }
            // Merge pre-fetched contents into the cache
            if (action.payload.contents) {
                Object.assign(state.contentCache, action.payload.contents)
            }
            state.isTreeLoading = false
            state.treeError = null
        },
        setTreeLoading: (state, action: PayloadAction<boolean>) => {
            state.isTreeLoading = action.payload
        },
        setTreeError: (state, action: PayloadAction<string | null>) => {
            state.treeError = action.payload
            state.isTreeLoading = false
        },
        setFileContent: (
            state,
            action: PayloadAction<FileContentPayload>
        ) => {
            const nextFile = buildOpenFile(action.payload)
            const { path } = action.payload

            if (nextFile.kind === 'text' || nextFile.kind === 'svg') {
                state.contentCache[path] = {
                    content: nextFile.content,
                    language: nextFile.language
                }
            }

            // Add or update the open file
            const existing = state.openFiles.findIndex(
                (f) => f.path === path
            )
            if (existing >= 0) {
                state.openFiles[existing] = nextFile
            } else {
                state.openFiles.push(nextFile)
            }
            state.activeFilePath = path
            state.isFileLoading = false
        },
        /** Open a file from cache — no backend round-trip needed. */
        openCachedFile: (state, action: PayloadAction<string>) => {
            const path = action.payload
            const cached = state.contentCache[path]
            if (!cached) return
            const existing = state.openFiles.findIndex(
                (f) => f.path === path
            )
            if (existing < 0) {
                state.openFiles.push(
                    buildTextLikeFile(path, cached.content, cached.language)
                )
            }
            state.activeFilePath = path
            state.isFileLoading = false
        },
        /** Update already-cached or currently open files from watcher events. */
        updateCachedContents: (
            state,
            action: PayloadAction<Record<string, CachedContent>>
        ) => {
            for (const [path, entry] of Object.entries(action.payload)) {
                const openIdx = state.openFiles.findIndex(
                    (f) => f.path === path
                )
                const shouldUpdateCache =
                    Boolean(state.contentCache[path]) || openIdx >= 0

                if (!shouldUpdateCache) {
                    continue
                }

                state.contentCache[path] = entry
                // If this file is currently open, update its displayed content
                if (
                    openIdx >= 0 &&
                    (state.openFiles[openIdx].kind === 'text' ||
                        state.openFiles[openIdx].kind === 'svg')
                ) {
                    state.openFiles[openIdx] = buildTextLikeFile(
                        path,
                        entry.content,
                        entry.language
                    )
                }
            }
        },
        markFilesChanged: (state, action: PayloadAction<string[]>) => {
            const changedPaths = new Set(action.payload)
            if (changedPaths.size === 0) return

            state.openFiles = state.openFiles.map((file) => {
                if (file.kind !== 'image' || !changedPaths.has(file.path)) {
                    return file
                }

                return {
                    ...file,
                    revision: file.revision + 1
                }
            })
        },
        setExplorerActiveFile: (state, action: PayloadAction<string>) => {
            state.activeFilePath = action.payload
        },
        closeFile: (state, action: PayloadAction<string>) => {
            const path = action.payload
            state.openFiles = state.openFiles.filter((f) => f.path !== path)
            if (state.activeFilePath === path) {
                state.activeFilePath =
                    state.openFiles.length > 0
                        ? state.openFiles[state.openFiles.length - 1].path
                        : null
            }
        },
        setFileLoading: (state, action: PayloadAction<boolean>) => {
            state.isFileLoading = action.payload
        },
        toggleDir: (state, action: PayloadAction<string>) => {
            const path = action.payload
            const idx = state.expandedDirs.indexOf(path)
            if (idx >= 0) {
                state.expandedDirs.splice(idx, 1)
            } else {
                state.expandedDirs.push(path)
            }
        },
        expandDir: (state, action: PayloadAction<string>) => {
            if (!state.expandedDirs.includes(action.payload)) {
                state.expandedDirs.push(action.payload)
            }
        },
        resetFileExplorer: () => initialState
    }
})

export const {
    setFileTree,
    setTreeLoading,
    setTreeError,
    setFileContent,
    openCachedFile,
    updateCachedContents,
    markFilesChanged,
    setExplorerActiveFile,
    closeFile,
    setFileLoading,
    toggleDir,
    expandDir,
    resetFileExplorer
} = fileExplorerSlice.actions

export const fileExplorerReducer = fileExplorerSlice.reducer

// Selectors
export const selectFileTree = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.tree

export const selectRootPath = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.rootPath

export const selectContentCache = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.contentCache

export const selectOpenFiles = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.openFiles

export const selectActiveFilePath = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.activeFilePath

export const selectActiveFile = (state: {
    fileExplorer: FileExplorerState
}) => {
    const { openFiles, activeFilePath } = state.fileExplorer
    if (!activeFilePath) return null
    return openFiles.find((f) => f.path === activeFilePath) ?? null
}

export const selectExpandedDirs = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.expandedDirs

export const selectIsTreeLoading = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.isTreeLoading

export const selectIsFileLoading = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.isFileLoading

export const selectTreeError = (state: {
    fileExplorer: FileExplorerState
}) => state.fileExplorer.treeError

