/**
 * Design Mode Types
 */

export interface ElementInfo {
    designId: string
    slideNumber?: number | null
    tagName: string
    className: string
    id: string
    textContent: string
    innerHTML: string
    outerHTML?: string
    contextText?: string
    prevSiblingText?: string
    nextSiblingText?: string
    reactSource?: {
        fileName?: string | null
        lineNumber?: number | null
        columnNumber?: number | null
        componentStack?: string[]
    } | null
    attributes?: Record<string, string>
    parentChain?: Array<{
        tag: string
        className: string
        id: string
    }>
    rect: {
        top: number
        left: number
        width: number
        height: number
        bottom: number
        right: number
    }
    computedStyles: {
        fontFamily: string
        fontSize: string
        fontWeight: string
        color: string
        backgroundColor: string
        borderRadius: string
        padding: string
        margin: string
        lineHeight?: string
        letterSpacing?: string
        textAlign?: string
        textDecorationLine?: string
        fontStyle?: string
        opacity?: string
        width?: string
        height?: string
        borderColor?: string
        borderStyle?: string
        borderWidth?: string
        boxShadow?: string
        backgroundImage?: string
        backgroundPosition?: string
        backgroundSize?: string
        backgroundRepeat?: string
        backgroundClip?: string
        webkitBackgroundClip?: string
        webkitTextFillColor?: string
        borderImageSource?: string
        textTransform?: string
    }
    xpath: string
}

export interface DesignChange {
    designId: string
    slideNumber?: number | null
    type: 'style' | 'text' | 'attribute' | 'move' | 'delete'
    property: string
    value: {
        from: string | null
        to: string | null
    }
    timestamp: number
    elementContext?: ElementInfo
    /**
     * Optional grouping metadata (e.g. for AI-applied multi-step edits).
     * When present, multiple DesignChange entries with the same `groupId`
     * should be treated as a single user-visible change set.
     */
    groupId?: string
    groupLabel?: string
}

export interface DesignModeDocumentSnapshotNode {
    designId: string
    tagName: string
    className: string
    id: string
    textContent: string
    attributes: Record<string, string>
    parentDesignId: string | null
    childDesignIds: string[]
    html: string
}

export interface DesignModeDocumentSnapshot {
    version: number
    generatedAt: number
    url: string
    title: string
    nodes: DesignModeDocumentSnapshotNode[]
}

export interface DesignModeState {
    isEnabled: boolean
    isReady: boolean
    isProxyMode: boolean
    selectedElement: ElementInfo | null
    hoveredElement: ElementInfo | null
    pendingChanges: DesignChange[]
    error: string | null
}

export type SyncProgress = {
    processed: number
    total: number
    applied?: number
    errors?: number
    current?: number
    done?: boolean
}

// Message types for iframe communication
export type DesignModeMessageType =
    | 'DESIGN_MODE_READY'
    | 'DESIGN_MODE_ENABLE'
    | 'DESIGN_MODE_DISABLE'
    | 'DESIGN_MODE_CLEAR_SELECTION'
    | 'DESIGN_MODE_ELEMENT_HOVER'
    | 'DESIGN_MODE_ELEMENT_SELECT'
    | 'DESIGN_MODE_ELEMENT_DOUBLE_CLICK'
    | 'DESIGN_MODE_GET_DECK_DIMENSIONS'
    | 'DESIGN_MODE_DECK_DIMENSIONS'
    | 'DESIGN_MODE_GET_DOCUMENT_SNAPSHOT'
    | 'DESIGN_MODE_DOCUMENT_SNAPSHOT'
    | 'DESIGN_MODE_SET_STYLE'
    | 'DESIGN_MODE_SET_TEXT'
    | 'DESIGN_MODE_SET_ATTRIBUTE'
    | 'DESIGN_MODE_SET_ICON'
    | 'DESIGN_MODE_MOVE_ELEMENT'
    | 'DESIGN_MODE_SWAP_ELEMENTS'
    | 'DESIGN_MODE_DELETE_ELEMENT'
    | 'DESIGN_MODE_RESTORE_ELEMENT'
    | 'DESIGN_MODE_SET_ELEMENT_LOADING'
    | 'DESIGN_MODE_CHANGE'
    | 'DESIGN_MODE_CLEAR_CHANGES'
    | 'DESIGN_MODE_REQUEST_SYNC'
    | 'DESIGN_MODE_SYNC_RESPONSE'
    | 'DESIGN_MODE_HIGHLIGHT_ELEMENT'
    | 'DESIGN_MODE_UNDO_REQUEST'
    | 'DESIGN_MODE_REDO_REQUEST'
    | 'DESIGN_MODE_TOGGLE_MULTI_SELECT'
    | 'DESIGN_MODE_MULTI_SELECT_CHANGE'

export interface DesignModeMessage {
    type: DesignModeMessageType
    payload?: unknown
}
