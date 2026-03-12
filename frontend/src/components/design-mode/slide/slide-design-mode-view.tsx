/**
 * Slide Design Mode View Component
 *
 * Displays a full slide deck (all slides stacked vertically) with design mode capabilities.
 * The deck HTML is fetched from the backend via slide-deck-proxy and includes the design runtime.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import axiosInstance from '@/lib/axios'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { addMessage, useAppDispatch, setBuildMode } from '@/state'
import { BUILD_MODE } from '@/typings'
import { useDesignModeContext } from '../design-mode-context'
import {
    loadDesignStateViaSocket,
    saveDesignStateViaSocket,
    syncSlideDeckStateViaSocket
} from '../design-mode-socket-state'
import { ErrorOverlay } from '../error-overlay'
import { SavingOverlay } from '../saving-overlay'
import { useSlideDeckScale } from './use-slide-deck-scale'
import type {
    ElementInfo,
    DesignChange,
    DesignModeDocumentSnapshot,
    DesignModeMessageType
} from '../types'
import {
    buildDesignChangeKey,
    buildDesignChangeKeyWithTimestamp
} from '../change-keys'

interface SlideDesignModeViewProps {
    sessionId: string
    presentationName: string
    slideCount?: number
    className?: string
}

export function SlideDesignModeView({
    sessionId,
    presentationName,
    className
}: SlideDesignModeViewProps) {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const { sendMessage: sendSocketMessage, isSessionReady } =
        useSocketIOContext()
    const iframeRef = useRef<HTMLIFrameElement>(null)
    const viewportRef = useRef<HTMLDivElement>(null)

    const [isDesignStateLoaded, setIsDesignStateLoaded] = useState(false)
    const [persistedChanges, setPersistedChanges] = useState<DesignChange[]>([])

    const [proxiedHtml, setProxiedHtml] = useState<string | null>(null)
    const [isProxyLoading, setIsProxyLoading] = useState(false)
    const [deckWidth, setDeckWidth] = useState(1280)
    const { scale, iframeUnscaledHeight } = useSlideDeckScale({
        viewportRef,
        deckWidth
    })

    const {
        isEnabled,
        isReady,
        isSaving,
        syncProgress,
        error,
        pendingChanges,
        redoChanges,
        selectedElement,
        setSelectedElement,
        setIsReady,
        setIsSaving,
        setError,
        addChange,
        replaceChanges,
        replaceRedoChanges,
        registerStyleHandlers,
        registerSaveHandler,
        clearChanges,
        undoLastChange,
        initSyncProgress
    } = useDesignModeContext()

    const isEnabledRef = useRef(isEnabled)
    useEffect(() => {
        isEnabledRef.current = isEnabled
    }, [isEnabled])

    const pendingChangesRef = useRef<DesignChange[]>(pendingChanges)
    useEffect(() => {
        pendingChangesRef.current = pendingChanges
    }, [pendingChanges])

    const redoChangesRef = useRef<DesignChange[]>(redoChanges)
    useEffect(() => {
        redoChangesRef.current = redoChanges
    }, [redoChanges])

    const mergeChanges = useCallback(
        (server: DesignChange[], local: DesignChange[]) => {
            const merged = new Map<string, DesignChange>()
            server.forEach((change) =>
                merged.set(buildDesignChangeKey(change), change)
            )
            local.forEach((change) =>
                merged.set(buildDesignChangeKey(change), change)
            )
            return Array.from(merged.values())
        },
        []
    )

    /**
     * Send a message to the iframe.
     */
    const sendMessage = useCallback((type: string, payload?: unknown) => {
        if (!iframeRef.current?.contentWindow) {
            console.warn('[SlideDesignModeView] No iframe window')
            return
        }
        iframeRef.current.contentWindow.postMessage({ type, payload }, '*')
    }, [])

    const sendMessageRef = useRef(sendMessage)
    sendMessageRef.current = sendMessage

    const snapshotRequestsRef = useRef(
        new Map<
            string,
            {
                resolve: (snapshot: DesignModeDocumentSnapshot | null) => void
                timeoutId: ReturnType<typeof setTimeout>
            }
        >()
    )

    const requestDocumentSnapshot = useCallback(
        async (options?: {
            maxNodes?: number
            maxTextLen?: number
            maxHtmlLen?: number
        }) => {
            if (!iframeRef.current?.contentWindow) {
                console.warn(
                    '[SlideDesignModeView] requestDocumentSnapshot: no iframe window'
                )
                return null
            }
            if (!isEnabled || !isReady) {
                console.warn(
                    '[SlideDesignModeView] requestDocumentSnapshot: not ready',
                    { isEnabled, isReady }
                )
                return null
            }

            const requestId = `snap-${Date.now()}-${Math.random()
                .toString(16)
                .slice(2)}`

            return await new Promise<DesignModeDocumentSnapshot | null>(
                (resolve) => {
                    const timeoutId = setTimeout(() => {
                        console.warn(
                            '[SlideDesignModeView] Document snapshot request timed out',
                            requestId
                        )
                        snapshotRequestsRef.current.delete(requestId)
                        resolve(null)
                    }, 2500)

                    snapshotRequestsRef.current.set(requestId, {
                        resolve,
                        timeoutId
                    })

                    sendMessageRef.current(
                        'DESIGN_MODE_GET_DOCUMENT_SNAPSHOT',
                        {
                            requestId,
                            options: options || {}
                        }
                    )
                }
            )
        },
        [isEnabled, isReady]
    )

    useEffect(() => {
        return () => {
            snapshotRequestsRef.current.forEach(({ timeoutId }) => {
                clearTimeout(timeoutId)
            })
            snapshotRequestsRef.current.clear()
        }
    }, [])

    /**
     * Load persisted design-mode changes from DB and hydrate the UI state.
     */
    useEffect(() => {
        if (!sessionId) {
            setIsDesignStateLoaded(true)
            setPersistedChanges([])
            return
        }

        setIsDesignStateLoaded(false)
        if (!isSessionReady) {
            return
        }

        let cancelled = false

        const load = async () => {
            try {
                const response = await loadDesignStateViaSocket(
                    sendSocketMessage,
                    sessionId
                )
                const serverChanges = Array.isArray(response?.changes)
                    ? (response.changes as DesignChange[])
                    : []
                const serverRedoChanges = Array.isArray(
                    response?.redo_changes
                )
                    ? (response.redo_changes as DesignChange[])
                    : []

                if (cancelled) return

                setPersistedChanges(serverChanges)
                setIsDesignStateLoaded(true)

                const localChanges = pendingChangesRef.current
                replaceChanges(mergeChanges(serverChanges, localChanges))

                if (redoChangesRef.current.length === 0) {
                    replaceRedoChanges(serverRedoChanges)
                }
            } catch (err) {
                console.error(
                    '[SlideDesignModeView] Failed to load persisted design state:',
                    err
                )
                if (cancelled) return
                setPersistedChanges([])
                setIsDesignStateLoaded(true)
            }
        }

        void load()
        return () => {
            cancelled = true
        }
    }, [
        sessionId,
        isSessionReady,
        sendSocketMessage,
        replaceChanges,
        mergeChanges,
        replaceRedoChanges
    ])

    useEffect(() => {
        const handleStateUpdated = (event: Event) => {
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

            const changes = Array.isArray(detail.changes)
                ? (detail.changes as DesignChange[])
                : []
            setPersistedChanges(changes)

            const redo = Array.isArray(detail.redo_changes)
                ? (detail.redo_changes as DesignChange[])
                : null
            if (redo) {
                replaceRedoChanges(redo)
            }
        }

        window.addEventListener(
            'design-mode-state-updated',
            handleStateUpdated as EventListener
        )
        return () => {
            window.removeEventListener(
                'design-mode-state-updated',
                handleStateUpdated as EventListener
            )
        }
    }, [sessionId, replaceRedoChanges])

    /**
     * Load proxied deck HTML from slide-deck-proxy endpoint.
     */
    useEffect(() => {
        let cancelled = false

        if (!isEnabled || !sessionId || !presentationName) {
            setIsProxyLoading(false)
            setProxiedHtml(null)
            return
        }

        setIsProxyLoading(true)
        setProxiedHtml(null)
        setIsReady(false)
        setError(null)

        const load = async () => {
            try {
                const response = await axiosInstance.get(
                    '/slides/design/slide-deck-proxy',
                    {
                        params: {
                            session_id: sessionId,
                            presentation_name: presentationName
                        },
                        responseType: 'text'
                    }
                )
                const html =
                    typeof response.data === 'string' ? response.data : null
                if (!html || !html.trim()) {
                    throw new Error('Empty proxy response')
                }

                if (cancelled) return
                setProxiedHtml(html)
                setIsProxyLoading(false)
            } catch (err) {
                console.error(
                    '[SlideDesignModeView] Failed to load slide deck proxy HTML:',
                    err
                )
                if (cancelled) return
                setIsProxyLoading(false)
                setProxiedHtml(null)

                let detail: string | null = null
                if (err && typeof err === 'object' && 'response' in err) {
                    const response = err.response as
                        | { data?: unknown }
                        | undefined
                    const responseData = response?.data

                    if (typeof responseData === 'string' && responseData) {
                        try {
                            const parsed: unknown = JSON.parse(responseData)
                            if (
                                parsed &&
                                typeof parsed === 'object' &&
                                'detail' in parsed &&
                                typeof parsed.detail === 'string'
                            ) {
                                detail = parsed.detail
                            }
                        } catch {
                            // ignore JSON parse errors
                        }
                    }
                }

                setError(detail || t('designMode.errors.failedToLoadPreview'))
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [isEnabled, sessionId, presentationName, setIsReady, setError, t])

    const hasAppliedPersistedChangesRef = useRef(false)
    useEffect(() => {
        hasAppliedPersistedChangesRef.current = false
    }, [proxiedHtml])

    useEffect(() => {
        if (!isEnabled || !isReady) return
        if (!isDesignStateLoaded) return
        if (hasAppliedPersistedChangesRef.current) return

        const changesToApply = mergeChanges(
            persistedChanges,
            pendingChangesRef.current
        ).sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))

        if (changesToApply.length === 0) {
            hasAppliedPersistedChangesRef.current = true
            return
        }

        changesToApply.forEach((change) => {
            const slideNumber =
                typeof change.slideNumber === 'number'
                    ? change.slideNumber
                    : undefined
            if (change.type === 'move') {
                const toValue = change.value?.to || ''
                if (!toValue) return

                if (
                    toValue === 'only' ||
                    toValue.startsWith('before:') ||
                    toValue.startsWith('after:')
                ) {
                    sendMessage('DESIGN_MODE_MOVE_ELEMENT', {
                        designId: change.designId,
                        slideNumber,
                        anchor: toValue,
                        xpath: change.elementContext?.xpath,
                        skipTracking: true
                    })
                    return
                }

                // Backward compatibility: earlier move changes used raw swap targets.
                sendMessage('DESIGN_MODE_SWAP_ELEMENTS', {
                    designId: change.designId,
                    slideNumber,
                    targetDesignId: toValue,
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
                return
            }
            if (change.type === 'attribute' && change.property === 'icon') {
                const raw = change.value?.to || ''
                if (!raw) return

                let iconName = ''
                let svgInner = ''
                try {
                    const parsed = JSON.parse(raw) as
                        | { name?: unknown; svg?: unknown }
                        | undefined
                    iconName =
                        parsed && typeof parsed.name === 'string'
                            ? parsed.name
                            : ''
                    svgInner =
                        parsed && typeof parsed.svg === 'string'
                            ? parsed.svg
                            : ''
                } catch {
                    svgInner = raw
                }

                if (!svgInner) return
                sendMessage('DESIGN_MODE_SET_ICON', {
                    designId: change.designId,
                    slideNumber,
                    iconName,
                    svgInner,
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
                return
            }

            if (change.type === 'text') {
                sendMessage('DESIGN_MODE_SET_TEXT', {
                    designId: change.designId,
                    slideNumber,
                    text: change.value?.to || '',
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
                return
            }

            if (change.type === 'delete') {
                sendMessage('DESIGN_MODE_DELETE_ELEMENT', {
                    designId: change.designId,
                    slideNumber,
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
                return
            }

            if (change.type === 'style') {
                sendMessage('DESIGN_MODE_SET_STYLE', {
                    designId: change.designId,
                    slideNumber,
                    property: change.property,
                    value: change.value?.to || '',
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
            }
        })

        hasAppliedPersistedChangesRef.current = true
    }, [
        isEnabled,
        isReady,
        isDesignStateLoaded,
        persistedChanges,
        mergeChanges,
        sendMessage
    ])

    /**
     * Handle messages from the iframe runtime.
     */
    useEffect(() => {
        const handleIframeMessage = (event: MessageEvent) => {
            if (
                iframeRef.current &&
                event.source !== iframeRef.current.contentWindow
            ) {
                return
            }

            const { type, payload } = event.data || {}

            switch (type) {
                case 'DESIGN_MODE_READY':
                    setIsReady(true)
                    setError(null)
                    if (isEnabledRef.current) {
                        sendMessageRef.current('DESIGN_MODE_ENABLE')
                    }
                    sendMessageRef.current('DESIGN_MODE_GET_DECK_DIMENSIONS')
                    break

                case 'DESIGN_MODE_ELEMENT_SELECT':
                    setSelectedElement(payload as ElementInfo | null)
                    break

                case 'DESIGN_MODE_ELEMENT_DOUBLE_CLICK':
                    setSelectedElement(payload as ElementInfo | null)
                    break

                case 'DESIGN_MODE_CHANGE':
                    addChange(payload as DesignChange)
                    break

                case 'DESIGN_MODE_UNDO_REQUEST':
                    undoLastChange()
                    break

                case 'DESIGN_MODE_DECK_DIMENSIONS': {
                    const width =
                        payload && typeof payload.width === 'number'
                            ? (payload.width as number)
                            : null
                    if (width && Number.isFinite(width) && width > 0) {
                        setDeckWidth(Math.round(width))
                    }
                    break
                }

                case 'DESIGN_MODE_DOCUMENT_SNAPSHOT': {
                    const requestId =
                        payload && typeof payload.requestId === 'string'
                            ? (payload.requestId as string)
                            : null
                    if (!requestId) {
                        console.warn(
                            '[SlideDesignModeView] Received snapshot without requestId'
                        )
                        break
                    }
                    const pending = snapshotRequestsRef.current.get(requestId)
                    if (!pending) break
                    clearTimeout(pending.timeoutId)
                    snapshotRequestsRef.current.delete(requestId)

                    const snapshot =
                        payload && typeof payload.snapshot === 'object'
                            ? (payload.snapshot as DesignModeDocumentSnapshot)
                            : null
                    pending.resolve(snapshot)
                    break
                }

                default:
                    break
            }
        }

        window.addEventListener('message', handleIframeMessage)
        return () => {
            window.removeEventListener('message', handleIframeMessage)
        }
    }, [
        setSelectedElement,
        setIsReady,
        setError,
        addChange,
        undoLastChange,
        setDeckWidth
    ])

    /**
     * When enabled and ready, send enable message.
     */
    useEffect(() => {
        if (isEnabled && isReady) {
            sendMessage('DESIGN_MODE_ENABLE')
        }
    }, [isEnabled, isReady, sendMessage])

    const persistTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const persistState = useCallback(
        async (changes: DesignChange[]) => {
            if (!sessionId || !isSessionReady) return
            try {
                const result = await saveDesignStateViaSocket(sendSocketMessage, {
                    sessionId,
                    changes,
                    redoChanges: redoChangesRef.current
                })
                window.dispatchEvent(
                    new CustomEvent('design-mode-state-updated', {
                        detail: {
                            session_id: result.session_id ?? sessionId,
                            changes: Array.isArray(result.changes)
                                ? result.changes
                                : changes,
                            redo_changes: Array.isArray(result.redo_changes)
                                ? result.redo_changes
                                : redoChangesRef.current
                        }
                    })
                )
            } catch (err) {
                console.warn(
                    '[SlideDesignModeView] Failed to persist design state',
                    err
                )
            }
        },
        [sessionId, isSessionReady, sendSocketMessage]
    )

    useEffect(() => {
        if (!isEnabled) return
        if (!sessionId) return
        if (!isDesignStateLoaded) return
        if (!isSessionReady) return
        if (isSaving) return

        if (persistTimeoutRef.current) {
            clearTimeout(persistTimeoutRef.current)
            persistTimeoutRef.current = null
        }

        persistTimeoutRef.current = setTimeout(() => {
            void persistState(pendingChangesRef.current)
        }, 1000)

        return () => {
            if (persistTimeoutRef.current) {
                clearTimeout(persistTimeoutRef.current)
                persistTimeoutRef.current = null
            }
        }
    }, [
        isDesignStateLoaded,
        isEnabled,
        isSaving,
        sessionId,
        pendingChanges,
        redoChanges,
        persistState,
        isSessionReady
    ])

    useEffect(() => {
        return () => {
            if (!sessionId) return
            if (!isDesignStateLoaded) return
            if (persistTimeoutRef.current) {
                clearTimeout(persistTimeoutRef.current)
                persistTimeoutRef.current = null
                void persistState(pendingChangesRef.current)
            }
        }
    }, [isDesignStateLoaded, sessionId, persistState])

    /**
     * Register style handlers with context.
     */
    useEffect(() => {
        registerStyleHandlers({
            setStyle: (property: string, value: string) => {
                if (!selectedElement) return
                sendMessage('DESIGN_MODE_SET_STYLE', {
                    designId: selectedElement.designId,
                    slideNumber:
                        typeof selectedElement.slideNumber === 'number'
                            ? selectedElement.slideNumber
                            : undefined,
                    property,
                    value
                })
            },
            setText: (text: string) => {
                if (!selectedElement) return
                sendMessage('DESIGN_MODE_SET_TEXT', {
                    designId: selectedElement.designId,
                    slideNumber:
                        typeof selectedElement.slideNumber === 'number'
                            ? selectedElement.slideNumber
                            : undefined,
                    text
                })
            },
            resetStyles: () => {
                // Not implemented for slides
            },
            revertChange: (change: DesignChange) => {
                const slideNumber =
                    typeof change.slideNumber === 'number'
                        ? change.slideNumber
                        : undefined

                if (change.type === 'move') {
                    const fromValue = change.value.from || ''
                    const toValue = change.value.to || ''
                    if (
                        fromValue === 'only' ||
                        fromValue.startsWith('before:') ||
                        fromValue.startsWith('after:')
                    ) {
                        sendMessageRef.current('DESIGN_MODE_MOVE_ELEMENT', {
                            designId: change.designId,
                            slideNumber,
                            anchor: fromValue,
                            xpath: change.elementContext?.xpath,
                            skipTracking: true
                        })
                        return
                    }

                    // Backward compatibility: earlier move changes used raw swap targets.
                    sendMessageRef.current('DESIGN_MODE_SWAP_ELEMENTS', {
                        designId: change.designId,
                        slideNumber,
                        targetDesignId: toValue,
                        xpath: change.elementContext?.xpath,
                        skipTracking: true
                    })
                    return
                }

                if (change.type === 'text') {
                    sendMessageRef.current('DESIGN_MODE_SET_TEXT', {
                        designId: change.designId,
                        slideNumber,
                        text: change.value.from || '',
                        skipTracking: true
                    })
                    return
                }

                if (change.type === 'delete') {
                    sendMessageRef.current('DESIGN_MODE_RESTORE_ELEMENT', {
                        designId: change.designId,
                        slideNumber,
                        xpath: change.elementContext?.xpath,
                        skipTracking: true
                    })
                    return
                }

                if (change.type === 'style') {
                    sendMessageRef.current('DESIGN_MODE_SET_STYLE', {
                        designId: change.designId,
                        slideNumber,
                        property: change.property,
                        value: change.value.from || '',
                        skipTracking: true
                    })
                }

                if (change.type === 'attribute' && change.property === 'icon') {
                    const raw = change.value.from || ''
                    if (!raw) return

                    let iconName = ''
                    let svgInner = ''
                    try {
                        const parsed = JSON.parse(raw) as
                            | { name?: unknown; svg?: unknown }
                            | undefined
                        iconName =
                            parsed && typeof parsed.name === 'string'
                                ? parsed.name
                                : ''
                        svgInner =
                            parsed && typeof parsed.svg === 'string'
                                ? parsed.svg
                                : ''
                    } catch {
                        svgInner = raw
                    }

                    if (!svgInner) return
                    sendMessageRef.current('DESIGN_MODE_SET_ICON', {
                        designId: change.designId,
                        slideNumber,
                        iconName,
                        svgInner,
                        skipTracking: true
                    })
                }
            },
            highlightElement: (designId: string) => {
                sendMessageRef.current('DESIGN_MODE_HIGHLIGHT_ELEMENT', {
                    designId
                })
            },
            setElementLoading: (designId: string, isLoading: boolean) => {
                sendMessageRef.current('DESIGN_MODE_SET_ELEMENT_LOADING', {
                    designId,
                    isLoading
                })
            },
            sendMessage: (type: DesignModeMessageType, payload?: unknown) => {
                sendMessageRef.current(type, payload)
            },
            requestDocumentSnapshot: requestDocumentSnapshot
        })
    }, [
        selectedElement,
        registerStyleHandlers,
        sendMessage,
        requestDocumentSnapshot
    ])

    /**
     * Save changes to DB + sync to sandbox.
     */
    const handleSaveChanges = useCallback(
        async (changesOverride?: DesignChange[]) => {
            if (!isSessionReady) {
                toast.error('Socket session is not ready. Please try again.')
                return
            }
            const changesToSync = Array.isArray(changesOverride)
                ? changesOverride
                : pendingChanges
            if (changesToSync.length === 0) return

            const selectedKeySet = Array.isArray(changesOverride)
                ? new Set(
                    changesToSync.map((change) =>
                        buildDesignChangeKeyWithTimestamp(change)
                    )
                )
                : null
            const unselectedChanges = selectedKeySet
                ? pendingChanges.filter(
                    (change) =>
                        !selectedKeySet.has(
                            buildDesignChangeKeyWithTimestamp(change)
                        )
                )
                : []

            // All style, text, icon, move/swap, and delete changes are supported
            // The backend will handle unsupported types by returning them as remaining changes
            const supportedChanges = changesToSync.filter(
                (c) =>
                    c.type === 'style' ||
                    c.type === 'text' ||
                    c.type === 'move' ||
                    c.type === 'delete' ||
                    (c.type === 'attribute' && c.property === 'icon')
            )

            // Log any unsupported changes for debugging, but don't block the sync
            const unsupportedChanges = changesToSync.filter(
                (c) =>
                    c.type !== 'style' &&
                    c.type !== 'text' &&
                    c.type !== 'move' &&
                    c.type !== 'delete' &&
                    !(c.type === 'attribute' && c.property === 'icon')
            )
            if (unsupportedChanges.length > 0) {
                console.warn(
                    '[SlideDesignModeView] Unsupported change types will be skipped:',
                    unsupportedChanges.map((c) => ({
                        type: c.type,
                        property: c.property
                    }))
                )
            }

            // If no supported changes, show error
            if (supportedChanges.length === 0) {
                toast.error(t('designMode.toasts.noSupportedChanges'))
                return
            }

            const payloadChanges = supportedChanges.map((c) => {
                const slideNumber =
                    typeof c.slideNumber === 'number' ? c.slideNumber : null
                return {
                    slide_number: slideNumber,
                    design_id: c.designId,
                    type: c.type,
                    property: c.property,
                    value: c.value
                }
            })

            const missingSlide = payloadChanges.some((c) => !c.slide_number)
            if (missingSlide) {
                toast.error(t('designMode.toasts.changesNotMappedToSlide'))
                return
            }

            // Initialize progress state before sync starts so UI shows 0/N immediately
            initSyncProgress(supportedChanges.length)
            setIsSaving(true)

            // Allow React to render the initial progress state before starting the sync
            await new Promise((resolve) => setTimeout(resolve, 0))

            try {
                // Ensure persisted state is up-to-date before syncing.
                await persistState(changesToSync)

                // Send sync command via socket and wait for completion event
                const syncResult = await syncSlideDeckStateViaSocket(
                    sendSocketMessage,
                    {
                        sessionId,
                        presentationName
                    }
                )

                const remainingChanges = Array.isArray(
                    syncResult?.remaining_changes
                )
                    ? (syncResult.remaining_changes as DesignChange[])
                    : []

                const mergedRemaining =
                    selectedKeySet !== null
                        ? [...unselectedChanges, ...remainingChanges]
                        : remainingChanges

                replaceChanges(mergedRemaining)

                const applied =
                    syncResult && typeof syncResult.applied === 'number'
                        ? (syncResult.applied as number)
                        : undefined
                const totalFromServer =
                    syncResult && typeof syncResult.total === 'number'
                        ? (syncResult.total as number)
                        : undefined
                const remainingFromServer =
                    syncResult &&
                        typeof syncResult.remaining === 'number'
                        ? (syncResult.remaining as number)
                        : undefined

                const summary =
                    typeof syncResult?.summary === 'string'
                        ? (syncResult.summary as string)
                        : applied !== undefined
                            ? t('designMode.messages.syncedSlideDesignChanges', {
                                count: applied
                            })
                            : t(
                                'designMode.messages.syncedSlideDesignChangesDefault'
                            )

                const eventId =
                    typeof syncResult?.event_id === 'string'
                        ? (syncResult.event_id as string)
                        : `${Date.now()}-slide-design-sync`

                dispatch(
                    addMessage({
                        id: eventId,
                        role: 'assistant',
                        content: summary,
                        timestamp: Date.now()
                    })
                )

                const isSyncSuccess = syncResult?.success === true
                if (isSyncSuccess) {
                    if (mergedRemaining.length === 0) {
                        clearChanges()
                        await persistState([])
                        sendMessageRef.current('DESIGN_MODE_CLEAR_CHANGES')
                    } else {
                        await persistState(mergedRemaining)
                    }
                    toast.success(
                        applied !== undefined
                            ? t('designMode.toasts.syncSuccessApplied', {
                                applied
                            })
                            : t('designMode.toasts.syncSuccess')
                    )
                } else if (
                    applied !== undefined &&
                    totalFromServer !== undefined &&
                    applied > 0 &&
                    remainingFromServer !== undefined &&
                    remainingFromServer > 0
                ) {
                    await persistState(mergedRemaining)
                    toast.message(
                        t('designMode.toasts.partialSync', {
                            applied,
                            total: totalFromServer
                        })
                    )
                } else {
                    await persistState(mergedRemaining)
                    toast.error(t('designMode.toasts.syncFailed'))
                }

                dispatch(setBuildMode(BUILD_MODE.BUILD))
            } catch (err) {
                console.error(
                    '[SlideDesignModeView] Failed to save changes:',
                    err
                )
                toast.error(t('designMode.toasts.saveFailed'))
            } finally {
                setIsSaving(false)
            }
        },
        [
            pendingChanges,
            sessionId,
            presentationName,
            clearChanges,
            replaceChanges,
            setIsSaving,
            initSyncProgress,
            persistState,
            dispatch,
            t,
            sendSocketMessage,
            isSessionReady
        ]
    )

    useEffect(() => {
        registerSaveHandler(handleSaveChanges)
    }, [registerSaveHandler, handleSaveChanges])

    return (
        <div
            className={cn(
                'relative w-full h-full flex flex-col overflow-hidden min-w-0',
                className
            )}
        >
            {/* Deck Iframe */}
            <div className="flex-1 relative bg-neutral-200 dark:bg-neutral-800">
                <SavingOverlay
                    isSaving={isSaving}
                    syncProgress={syncProgress}
                    zIndex={30}
                />
                <div className="absolute inset-0 overflow-hidden p-4">
                    <div
                        ref={viewportRef}
                        className="w-full h-full flex items-start justify-center"
                    >
                        {proxiedHtml && (
                            <div
                                className="bg-white shadow-2xl rounded-lg overflow-hidden flex-shrink-0 w-full"
                                style={{ maxWidth: deckWidth * scale }}
                            >
                                <div
                                    className="w-full overflow-hidden relative"
                                    style={{
                                        height: iframeUnscaledHeight * scale
                                    }}
                                >
                                    <div
                                        className="absolute top-0 left-0"
                                        style={{
                                            width: deckWidth,
                                            transform: `scale(${scale})`,
                                            transformOrigin: 'top left'
                                        }}
                                    >
                                        <iframe
                                            ref={iframeRef}
                                            srcDoc={proxiedHtml}
                                            className={cn(
                                                'border-0 bg-white',
                                                isEnabled && 'cursor-crosshair'
                                            )}
                                            style={{
                                                width: deckWidth,
                                                height: iframeUnscaledHeight
                                            }}
                                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-presentation"
                                            title={t('common.preview')}
                                        />
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {isProxyLoading && (
                    <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/70 dark:bg-neutral-950/70">
                        <Loader2 className="h-8 w-8 animate-spin text-sky-blue" />
                    </div>
                )}
            </div>

            {/* Error Overlay */}
            <ErrorOverlay error={isEnabled ? error : null} />
        </div>
    )
}
