/**
 * Design Mode Context
 *
 * Provides shared design mode state between the iframe preview and chat area.
 */

import {
    createContext,
    useContext,
    useState,
    useCallback,
    useEffect,
    useRef,
    type ReactNode
} from 'react'
import { buildDesignChangeKey, normalizeSlideNumber } from './change-keys'
import type {
    ElementInfo,
    DesignChange,
    DesignModeDocumentSnapshot,
    DesignModeMessageType,
    SyncProgress
} from './types'

interface DesignModeContextValue {
    // State
    isEnabled: boolean
    isReady: boolean
    isSaving: boolean
    syncProgress: SyncProgress | null
    selectedElement: ElementInfo | null
    pendingChanges: DesignChange[]
    redoChanges: DesignChange[]
    error: string | null
    isMultiSelectMode: boolean
    multiSelectedElements: ElementInfo[]
    isInteractMode: boolean

    // Actions
    enable: () => void
    disable: () => void
    toggle: () => void
    setIsSaving: (saving: boolean) => void
    setSelectedElement: (element: ElementInfo | null) => void
    setIsReady: (ready: boolean) => void
    setError: (error: string | null) => void
    addChange: (change: DesignChange) => void
    removeChange: (
        designId: string,
        type: string,
        property: string,
        slideNumber?: number | null
    ) => void
    clearChanges: () => void
    replaceChanges: (changes: DesignChange[]) => void
    openChangesPanel: () => void
    registerChangesPanelHandler: (handler: () => void) => void
    saveChanges: (changes?: DesignChange[]) => void
    registerSaveHandler: (handler: (changes?: DesignChange[]) => void) => void
    undoLastChange: () => void
    redoLastChange: () => void
    replaceRedoChanges: (changes: DesignChange[]) => void
    initSyncProgress: (total: number) => void

    // Style/text change functions (set by wrapper)
    setStyle: (property: string, value: string) => void
    setText: (text: string) => void
    setStyleByDesignId: (
        designId: string,
        property: string,
        value: string,
        options?: {
            xpath?: string
            skipTracking?: boolean
            slideNumber?: number | null
            groupId?: string
            groupLabel?: string
        }
    ) => void
    setTextByDesignId: (
        designId: string,
        text: string,
        options?: {
            xpath?: string
            skipTracking?: boolean
            slideNumber?: number | null
            groupId?: string
            groupLabel?: string
        }
    ) => void
    setIconByDesignId: (
        designId: string,
        iconName: string,
        svgInner: string,
        options?: { xpath?: string; skipTracking?: boolean }
    ) => void
    moveElementByDesignId: (
        designId: string,
        anchor: string,
        options?: { skipTracking?: boolean }
    ) => void
    swapElementsByDesignId: (
        designId: string,
        targetDesignId: string,
        options?: { skipTracking?: boolean }
    ) => void
    deleteElementByDesignId: (
        designId: string,
        options?: { xpath?: string; skipTracking?: boolean }
    ) => void
    deleteSelectedElements: () => void
    toggleMultiSelectMode: () => void
    toggleInteractMode: () => void
    addToMultiSelect: (element: ElementInfo) => void
    removeFromMultiSelect: (designId: string) => void
    clearMultiSelect: () => void
    setMultiSelectElements: (elements: ElementInfo[]) => void
    resetStyles: () => void
    revertChange: (change: DesignChange) => void
    highlightElement: (designId: string) => void
    setElementLoading: (designId: string, isLoading: boolean) => void
    clearSelection: () => void
    requestDocumentSnapshot: (options?: {
        maxNodes?: number
        maxTextLen?: number
        maxHtmlLen?: number
    }) => Promise<DesignModeDocumentSnapshot | null>
    registerStyleHandlers: (handlers: {
        setStyle: (property: string, value: string) => void
        setText: (text: string) => void
        resetStyles: () => void
        revertChange: (change: DesignChange) => void
        highlightElement: (designId: string) => void
        setElementLoading: (designId: string, isLoading: boolean) => void
        sendMessage: (type: DesignModeMessageType, payload?: unknown) => void
        requestDocumentSnapshot: (options?: {
            maxNodes?: number
            maxTextLen?: number
            maxHtmlLen?: number
        }) => Promise<DesignModeDocumentSnapshot | null>
    }) => void
}

function upsertDesignChange(
    prev: DesignChange[],
    change: DesignChange
): DesignChange[] {
    const nextKey = buildDesignChangeKey(change)
    const existingIndex = prev.findIndex(
        (c) => buildDesignChangeKey(c) === nextKey
    )

    if (existingIndex >= 0) {
        const existing = prev[existingIndex]
        const originalFrom = existing.value.from

        // If new value equals original, remove the change entirely
        if (change.value.to === originalFrom) {
            return prev.filter((_, i) => i !== existingIndex)
        }

        // Otherwise update the 'to' value while preserving original 'from'
        const updated = [...prev]
        updated[existingIndex] = {
            ...change,
            value: {
                from: originalFrom,
                to: change.value.to
            },
            timestamp: change.timestamp
        }
        return updated
    }

    // If new value equals the original 'from' value, don't add the change
    if (change.value.to === change.value.from) {
        return prev
    }

    return [...prev, change]
}

const DesignModeContext = createContext<DesignModeContextValue | null>(null)

export function DesignModeProvider({
    children,
    sessionId
}: {
    children: ReactNode
    sessionId?: string
}) {
    const [isEnabled, setIsEnabled] = useState(false)
    const [isReady, setIsReady] = useState(false)
    const [isSaving, setIsSaving] = useState(false)
    const [syncProgress, setSyncProgress] = useState<SyncProgress | null>(null)
    const [selectedElement, setSelectedElement] = useState<ElementInfo | null>(
        null
    )
    const [pendingChanges, setPendingChanges] = useState<DesignChange[]>([])
    const [redoChanges, setRedoChanges] = useState<DesignChange[]>([])
    // Ref to access current redoChanges without stale closure issues
    const redoChangesRef = useRef<DesignChange[]>([])
    redoChangesRef.current = redoChanges
    const [error, setError] = useState<string | null>(null)
    const [isMultiSelectMode, setIsMultiSelectMode] = useState(false)
    const [multiSelectedElements, setMultiSelectedElements] = useState<
        ElementInfo[]
    >([])
    const [isInteractMode, setIsInteractMode] = useState(false)

    // These will be set by the wrapper component
    const [styleHandlers, setStyleHandlers] = useState<{
        setStyle: (property: string, value: string) => void
        setText: (text: string) => void
        resetStyles: () => void
        revertChange: (change: DesignChange) => void
        highlightElement: (designId: string) => void
        setElementLoading: (designId: string, isLoading: boolean) => void
        sendMessage: (type: DesignModeMessageType, payload?: unknown) => void
        requestDocumentSnapshot: (options?: {
            maxNodes?: number
            maxTextLen?: number
            maxHtmlLen?: number
        }) => Promise<DesignModeDocumentSnapshot | null>
    } | null>(null)

    // Changes panel handler (set by chat-box)
    const [changesPanelHandler, setChangesPanelHandler] = useState<
        (() => void) | null
    >(null)

    // Save handler (set by preview integration)
    const [saveHandler, setSaveHandler] = useState<
        ((changes?: DesignChange[]) => void) | null
    >(null)

    const undoLastChange = useCallback(() => {
        if (!isEnabled) return
        if (!styleHandlers) return
        if (pendingChanges.length === 0) return

        const latest = pendingChanges.reduce((acc, change) =>
            change.timestamp > acc.timestamp ? change : acc
        )

        const groupId = latest.groupId
        const toUndo = groupId
            ? pendingChanges.filter((change) => change.groupId === groupId)
            : [latest]

        // Revert in reverse order for safer multi-step changes.
        const ordered = [...toUndo].sort(
            (a, b) => (b.timestamp || 0) - (a.timestamp || 0)
        )
        for (const change of ordered) {
            styleHandlers.revertChange(change)
        }

        const toRedo = [...toUndo].sort(
            (a, b) => (a.timestamp || 0) - (b.timestamp || 0)
        )
        setRedoChanges((prev) => [...prev, ...toRedo])

        const keys = new Set(toUndo.map(buildDesignChangeKey))
        setPendingChanges((prev) =>
            prev.filter((change) => !keys.has(buildDesignChangeKey(change)))
        )
    }, [isEnabled, pendingChanges, styleHandlers])

    const redoLastChange = useCallback(() => {
        if (!isEnabled) return
        if (!styleHandlers) return

        // Use ref for reading to avoid stale closure issues with rapid successive calls
        const currentRedoChanges = redoChangesRef.current
        if (currentRedoChanges.length === 0) return

        const last = currentRedoChanges[currentRedoChanges.length - 1]
        const groupId = last.groupId

        const startIndex = (() => {
            if (!groupId) return currentRedoChanges.length - 1
            for (let i = currentRedoChanges.length - 1; i >= 0; i -= 1) {
                if (currentRedoChanges[i]?.groupId !== groupId) return i + 1
            }
            return 0
        })()

        const batch = currentRedoChanges.slice(startIndex)
        // Use functional update to ensure atomic state update
        setRedoChanges((prev) => prev.slice(0, prev.length - batch.length))

        const baseTimestamp = Date.now()

        const parseIconPayload = (
            raw: string | null
        ): { iconName: string; svgInner: string } | null => {
            if (!raw) return null
            try {
                const parsed = JSON.parse(raw) as
                    | { name?: unknown; svg?: unknown }
                    | undefined
                const iconName =
                    parsed && typeof parsed.name === 'string' ? parsed.name : ''
                const svgInner =
                    parsed && typeof parsed.svg === 'string' ? parsed.svg : ''
                if (!svgInner) return null
                return { iconName, svgInner }
            } catch {
                return { iconName: '', svgInner: raw }
            }
        }

        batch.forEach((change, index) => {
            const designId = change.designId
            const xpath = change.elementContext?.xpath
            const slideNumber =
                typeof change.slideNumber === 'number'
                    ? change.slideNumber
                    : typeof change.elementContext?.slideNumber === 'number'
                        ? change.elementContext.slideNumber
                        : undefined

            if (change.type === 'move') {
                const toValue = change.value.to || ''
                if (
                    toValue === 'only' ||
                    toValue.startsWith('before:') ||
                    toValue.startsWith('after:')
                ) {
                    styleHandlers.sendMessage('DESIGN_MODE_MOVE_ELEMENT', {
                        designId,
                        anchor: toValue,
                        skipTracking: true
                    })
                } else if (toValue) {
                    styleHandlers.sendMessage('DESIGN_MODE_SWAP_ELEMENTS', {
                        designId,
                        targetDesignId: toValue,
                        skipTracking: true
                    })
                }
            } else if (change.type === 'text') {
                styleHandlers.sendMessage('DESIGN_MODE_SET_TEXT', {
                    designId,
                    slideNumber,
                    text: change.value.to || '',
                    xpath,
                    skipTracking: true
                })
            } else if (change.type === 'delete') {
                styleHandlers.sendMessage('DESIGN_MODE_DELETE_ELEMENT', {
                    designId,
                    slideNumber,
                    xpath,
                    skipTracking: true
                })
            } else if (
                change.type === 'attribute' &&
                change.property === 'icon'
            ) {
                const payload = parseIconPayload(change.value.to || '')
                if (payload) {
                    styleHandlers.sendMessage('DESIGN_MODE_SET_ICON', {
                        designId,
                        iconName: payload.iconName,
                        svgInner: payload.svgInner,
                        xpath,
                        skipTracking: true
                    })
                }
            } else if (change.type === 'style') {
                styleHandlers.sendMessage('DESIGN_MODE_SET_STYLE', {
                    designId,
                    slideNumber,
                    property: change.property,
                    value: change.value.to || '',
                    xpath,
                    skipTracking: true
                })
            }

            const updated: DesignChange = {
                ...change,
                timestamp: baseTimestamp + index
            }
            setPendingChanges((prev) => upsertDesignChange(prev, updated))
        })
    }, [isEnabled, styleHandlers])

    const replaceRedoChanges = useCallback((changes: DesignChange[]) => {
        setRedoChanges(changes)
    }, [])

    useEffect(() => {
        const isEditableTarget = (target: EventTarget | null) => {
            if (!target || !(target instanceof HTMLElement)) return false
            const tag = target.tagName.toLowerCase()
            if (tag === 'input' || tag === 'textarea' || tag === 'select')
                return true
            return target.isContentEditable
        }

        const onKeyDown = (e: KeyboardEvent) => {
            if (!isEnabled) return
            if (e.defaultPrevented) return
            if (e.altKey) return
            if (!(e.ctrlKey || e.metaKey)) return
            const key = (e.key || '').toLowerCase()
            const isToggleChanges = key === 's'
            const isUndo = key === 'z' && !e.shiftKey
            const isRedo =
                key === 'y' ||
                (key === 'z' && e.shiftKey && (e.ctrlKey || e.metaKey))
            if (!isToggleChanges && !isUndo && !isRedo) return
            if (isEditableTarget(e.target)) return

            e.preventDefault()
            if (isToggleChanges) {
                changesPanelHandler?.()
                return
            }
            if (isUndo) {
                undoLastChange()
                return
            }
            redoLastChange()
        }

        window.addEventListener('keydown', onKeyDown, { capture: true })
        return () => {
            window.removeEventListener('keydown', onKeyDown, { capture: true })
        }
    }, [changesPanelHandler, isEnabled, undoLastChange, redoLastChange])

    const previousSessionIdRef = useRef(sessionId)
    useEffect(() => {
        if (previousSessionIdRef.current === sessionId) return
        previousSessionIdRef.current = sessionId

        // Reset only session-scoped state to avoid cross-session bleed.
        setIsEnabled(false)
        setIsReady(false)
        setIsSaving(false)
        setSyncProgress(null)
        setSelectedElement(null)
        setPendingChanges([])
        setRedoChanges([])
        setError(null)
        setIsMultiSelectMode(false)
        setMultiSelectedElements([])
        setIsInteractMode(false)
        setStyleHandlers(null)
    }, [sessionId])

    useEffect(() => {
        if (!isSaving) {
            setSyncProgress(null)
        }
    }, [isSaving])

    useEffect(() => {
        const handleProgressEvent = (event: Event) => {
            const detail = (event as CustomEvent).detail as
                | Record<string, unknown>
                | undefined
            if (!detail || typeof detail !== 'object') return

            const sessionIdFromEvent = detail.session_id
            if (
                sessionId &&
                typeof sessionIdFromEvent === 'string' &&
                sessionIdFromEvent &&
                sessionIdFromEvent !== sessionId
            ) {
                return
            }

            const processedRaw = detail.processed
            const totalRaw = detail.total
            const processed =
                typeof processedRaw === 'number'
                    ? processedRaw
                    : Number(processedRaw)
            const total =
                typeof totalRaw === 'number' ? totalRaw : Number(totalRaw)
            if (!Number.isFinite(processed) || !Number.isFinite(total)) return

            const appliedRaw = detail.applied
            const errorsRaw = detail.errors
            const currentRaw = detail.current

            const applied =
                typeof appliedRaw === 'number'
                    ? appliedRaw
                    : appliedRaw !== undefined
                        ? Number(appliedRaw)
                        : undefined
            const errorsCount =
                typeof errorsRaw === 'number'
                    ? errorsRaw
                    : errorsRaw !== undefined
                        ? Number(errorsRaw)
                        : undefined
            const current =
                typeof currentRaw === 'number'
                    ? currentRaw
                    : currentRaw !== undefined
                        ? Number(currentRaw)
                        : undefined

            setSyncProgress({
                processed,
                total,
                applied: Number.isFinite(applied as number)
                    ? applied
                    : undefined,
                errors: Number.isFinite(errorsCount as number)
                    ? errorsCount
                    : undefined,
                current: Number.isFinite(current as number)
                    ? current
                    : undefined,
                done: detail.done === true
            })
        }

        window.addEventListener(
            'design-mode-sync-progress',
            handleProgressEvent as EventListener
        )
        return () => {
            window.removeEventListener(
                'design-mode-sync-progress',
                handleProgressEvent as EventListener
            )
        }
    }, [sessionId])

    const enable = useCallback(() => {
        setIsEnabled(true)
        setIsReady(false)
        setIsSaving(false)
        setError(null)
    }, [])

    const disable = useCallback(() => {
        setIsEnabled(false)
        setIsReady(false)
        setIsSaving(false)
        setSelectedElement(null)
        setError(null)
        setIsMultiSelectMode(false)
        setMultiSelectedElements([])
        setIsInteractMode(false)
    }, [])

    const toggle = useCallback(() => {
        if (isEnabled) {
            disable()
        } else {
            enable()
        }
    }, [isEnabled, enable, disable])

    const addChange = useCallback((change: DesignChange) => {
        // Any new change invalidates the redo stack.
        setRedoChanges([])
        setPendingChanges((prev) => upsertDesignChange(prev, change))
    }, [])

    const replaceChanges = useCallback((changes: DesignChange[]) => {
        setPendingChanges(changes)
    }, [])

    const clearChanges = useCallback(() => {
        setPendingChanges([])
    }, [])

    const removeChange = useCallback(
        (
            designId: string,
            type: string,
            property: string,
            slideNumber?: number | null
        ) => {
            const normalizedSlide = normalizeSlideNumber(slideNumber)
            const keyToRemove = buildDesignChangeKey({
                designId,
                type: type as DesignChange['type'],
                property,
                slideNumber: normalizedSlide
            })
            setPendingChanges((prev) =>
                prev.filter((c) => buildDesignChangeKey(c) !== keyToRemove)
            )
        },
        []
    )

    const registerStyleHandlers = useCallback(
        (handlers: {
            setStyle: (property: string, value: string) => void
            setText: (text: string) => void
            resetStyles: () => void
            revertChange: (change: DesignChange) => void
            highlightElement: (designId: string) => void
            setElementLoading: (designId: string, isLoading: boolean) => void
            sendMessage: (
                type: DesignModeMessageType,
                payload?: unknown
            ) => void
            requestDocumentSnapshot: (options?: {
                maxNodes?: number
                maxTextLen?: number
                maxHtmlLen?: number
            }) => Promise<DesignModeDocumentSnapshot | null>
        }) => {
            setStyleHandlers(handlers)
        },
        []
    )

    const setStyle = useCallback(
        (property: string, value: string) => {
            styleHandlers?.setStyle(property, value)
        },
        [styleHandlers]
    )

    const setText = useCallback(
        (text: string) => {
            styleHandlers?.setText(text)
        },
        [styleHandlers]
    )

    const setStyleByDesignId = useCallback(
        (
            designId: string,
            property: string,
            value: string,
            options?: {
                xpath?: string
                skipTracking?: boolean
                slideNumber?: number | null
                groupId?: string
                groupLabel?: string
            }
        ) => {
            styleHandlers?.sendMessage('DESIGN_MODE_SET_STYLE', {
                designId,
                slideNumber:
                    typeof options?.slideNumber === 'number'
                        ? options.slideNumber
                        : undefined,
                property,
                value,
                xpath: options?.xpath,
                skipTracking: options?.skipTracking,
                groupId: options?.groupId,
                groupLabel: options?.groupLabel
            })
        },
        [styleHandlers]
    )

    const setTextByDesignId = useCallback(
        (
            designId: string,
            text: string,
            options?: {
                xpath?: string
                skipTracking?: boolean
                slideNumber?: number | null
                groupId?: string
                groupLabel?: string
            }
        ) => {
            styleHandlers?.sendMessage('DESIGN_MODE_SET_TEXT', {
                designId,
                slideNumber:
                    typeof options?.slideNumber === 'number'
                        ? options.slideNumber
                        : undefined,
                text,
                xpath: options?.xpath,
                skipTracking: options?.skipTracking,
                groupId: options?.groupId,
                groupLabel: options?.groupLabel
            })
        },
        [styleHandlers]
    )

    const setIconByDesignId = useCallback(
        (
            designId: string,
            iconName: string,
            svgInner: string,
            options?: { xpath?: string; skipTracking?: boolean }
        ) => {
            styleHandlers?.sendMessage('DESIGN_MODE_SET_ICON', {
                designId,
                iconName,
                svgInner,
                xpath: options?.xpath,
                skipTracking: options?.skipTracking
            })
        },
        [styleHandlers]
    )

    const moveElementByDesignId = useCallback(
        (
            designId: string,
            anchor: string,
            options?: { skipTracking?: boolean }
        ) => {
            styleHandlers?.sendMessage('DESIGN_MODE_MOVE_ELEMENT', {
                designId,
                anchor,
                skipTracking: options?.skipTracking
            })
        },
        [styleHandlers]
    )

    const swapElementsByDesignId = useCallback(
        (
            designId: string,
            targetDesignId: string,
            options?: { skipTracking?: boolean }
        ) => {
            styleHandlers?.sendMessage('DESIGN_MODE_SWAP_ELEMENTS', {
                designId,
                targetDesignId,
                skipTracking: options?.skipTracking
            })
        },
        [styleHandlers]
    )

    const deleteElementByDesignId = useCallback(
        (
            designId: string,
            options?: { xpath?: string; skipTracking?: boolean }
        ) => {
            styleHandlers?.sendMessage('DESIGN_MODE_DELETE_ELEMENT', {
                designId,
                xpath: options?.xpath,
                skipTracking: options?.skipTracking
            })
        },
        [styleHandlers]
    )

    const toggleInteractMode = useCallback(() => {
        setIsInteractMode((prev) => {
            const next = !prev
            if (next) {
                // Entering interact mode: disable design selection in iframe
                styleHandlers?.sendMessage('DESIGN_MODE_DISABLE')
            } else {
                // Exiting interact mode: re-enable design selection in iframe
                styleHandlers?.sendMessage('DESIGN_MODE_ENABLE')
            }
            return next
        })
    }, [styleHandlers])

    const toggleMultiSelectMode = useCallback(() => {
        setIsMultiSelectMode((prev) => {
            if (prev) {
                // Exiting multi-select mode, clear selections
                setMultiSelectedElements([])
            }
            styleHandlers?.sendMessage('DESIGN_MODE_TOGGLE_MULTI_SELECT', {
                enabled: !prev
            })
            return !prev
        })
    }, [styleHandlers])

    const addToMultiSelect = useCallback((element: ElementInfo) => {
        setMultiSelectedElements((prev) => {
            if (prev.some((el) => el.designId === element.designId)) {
                return prev
            }
            return [...prev, element]
        })
    }, [])

    const removeFromMultiSelect = useCallback((designId: string) => {
        setMultiSelectedElements((prev) =>
            prev.filter((el) => el.designId !== designId)
        )
    }, [])

    const clearMultiSelect = useCallback(() => {
        setMultiSelectedElements([])
    }, [])

    const setMultiSelectElements = useCallback((elements: ElementInfo[]) => {
        setMultiSelectedElements(elements)
    }, [])

    const deleteSelectedElements = useCallback(() => {
        if (multiSelectedElements.length === 0) return

        const groupId = `delete-${Date.now()}`
        const groupLabel = `Delete ${multiSelectedElements.length} elements`

        multiSelectedElements.forEach((element) => {
            // Send delete message to iframe
            styleHandlers?.sendMessage('DESIGN_MODE_DELETE_ELEMENT', {
                designId: element.designId,
                xpath: element.xpath,
                skipTracking: false,
                groupId,
                groupLabel
            })
        })

        // Clear multi-select after deleting
        setMultiSelectedElements([])
        setIsMultiSelectMode(false)
        setSelectedElement(null)
        styleHandlers?.sendMessage('DESIGN_MODE_TOGGLE_MULTI_SELECT', {
            enabled: false
        })
    }, [multiSelectedElements, styleHandlers, setSelectedElement])

    const resetStyles = useCallback(() => {
        styleHandlers?.resetStyles()
    }, [styleHandlers])

    const revertChange = useCallback(
        (change: DesignChange) => {
            styleHandlers?.revertChange(change)
            // Remove the change from pending changes after reverting
            removeChange(
                change.designId,
                change.type,
                change.property,
                change.slideNumber
            )
        },
        [styleHandlers, removeChange]
    )

    const highlightElement = useCallback(
        (designId: string) => {
            styleHandlers?.highlightElement(designId)
        },
        [styleHandlers]
    )

    const setElementLoading = useCallback(
        (designId: string, isLoading: boolean) => {
            styleHandlers?.setElementLoading(designId, isLoading)
        },
        [styleHandlers]
    )

    const clearSelection = useCallback(() => {
        setSelectedElement(null)
        styleHandlers?.sendMessage('DESIGN_MODE_CLEAR_SELECTION')
    }, [styleHandlers])

    const requestDocumentSnapshot = useCallback(
        (options?: {
            maxNodes?: number
            maxTextLen?: number
            maxHtmlLen?: number
        }) =>
            styleHandlers?.requestDocumentSnapshot(options) ??
            Promise.resolve(null),
        [styleHandlers]
    )

    const registerChangesPanelHandler = useCallback((handler: () => void) => {
        setChangesPanelHandler(() => handler)
    }, [])

    const openChangesPanel = useCallback(() => {
        changesPanelHandler?.()
    }, [changesPanelHandler])

    const registerSaveHandler = useCallback(
        (handler: (changes?: DesignChange[]) => void) => {
            setSaveHandler(() => handler)
        },
        []
    )

    const saveChanges = useCallback(
        (changes?: DesignChange[]) => {
            saveHandler?.(changes)
        },
        [saveHandler]
    )

    const initSyncProgress = useCallback((total: number) => {
        // Initialize progress state before sync starts to ensure UI shows 0/N
        setSyncProgress({
            processed: 0,
            total,
            applied: undefined,
            errors: undefined,
            current: total > 0 ? 1 : undefined,
            done: false
        })
    }, [])

    return (
        <DesignModeContext.Provider
            value={{
                isEnabled,
                isReady,
                isSaving,
                syncProgress,
                selectedElement,
                pendingChanges,
                redoChanges,
                error,
                isMultiSelectMode,
                multiSelectedElements,
                isInteractMode,
                enable,
                disable,
                toggle,
                setIsSaving,
                setSelectedElement,
                setIsReady,
                setError,
                addChange,
                removeChange,
                clearChanges,
                replaceChanges,
                openChangesPanel,
                registerChangesPanelHandler,
                saveChanges,
                registerSaveHandler,
                undoLastChange,
                redoLastChange,
                replaceRedoChanges,
                initSyncProgress,
                setStyle,
                setText,
                setStyleByDesignId,
                setTextByDesignId,
                setIconByDesignId,
                moveElementByDesignId,
                swapElementsByDesignId,
                deleteElementByDesignId,
                deleteSelectedElements,
                toggleMultiSelectMode,
                toggleInteractMode,
                addToMultiSelect,
                removeFromMultiSelect,
                clearMultiSelect,
                setMultiSelectElements,
                resetStyles,
                revertChange,
                highlightElement,
                setElementLoading,
                clearSelection,
                requestDocumentSnapshot,
                registerStyleHandlers
            }}
        >
            {children}
        </DesignModeContext.Provider>
    )
}

export function useDesignModeContext() {
    const context = useContext(DesignModeContext)
    if (!context) {
        throw new Error(
            'useDesignModeContext must be used within a DesignModeProvider'
        )
    }
    return context
}

export function useOptionalDesignModeContext() {
    return useContext(DesignModeContext)
}
