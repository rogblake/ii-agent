/**
 * Design Mode Wrapper Component
 *
 * Wraps an iframe preview with design mode capabilities.
 * Shows only a status indicator when design mode is active.
 * The inspector sidebar and controls are in the chat area (Design tab).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import axiosInstance from '@/lib/axios'
import { addMessage, setBuildMode, useAppDispatch } from '@/state'
import { BUILD_MODE } from '@/typings'
import { useDesignModeContext } from './design-mode-context'
import {
    DEVICE_PRESETS,
    TRACKED_PROPERTIES,
    type DevicePreset
} from './device-presets'
import { ErrorOverlay } from './error-overlay'
import { IframePreview } from './iframe-preview'
import type {
    ElementInfo,
    DesignChange,
    DesignModeDocumentSnapshot,
    DesignModeMessageType
} from './types'
import {
    buildDesignChangeKey,
    buildDesignChangeKeyWithTimestamp
} from './change-keys'

interface DesignModeWrapperProps {
    /** The iframe source URL (direct sandbox URL) */
    src: string
    /** Session ID for API calls */
    sessionId?: string
    /** Device preset id (preview sizing) */
    deviceId?: DevicePreset['id']
    /** Additional class name for the container */
    className?: string
    /** Additional class name for the iframe */
    iframeClassName?: string
}

export function DesignModeWrapper({
    src,
    sessionId,
    deviceId,
    className,
    iframeClassName
}: DesignModeWrapperProps) {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const iframeRef = useRef<HTMLIFrameElement>(null)

    const [isDesignStateLoaded, setIsDesignStateLoaded] = useState(false)
    const [persistedChanges, setPersistedChanges] = useState<DesignChange[]>([])

    const selectedDevice = useMemo(() => {
        if (deviceId) {
            const found = DEVICE_PRESETS.find((d) => d.id === deviceId)
            if (found) return found
        }
        return DEVICE_PRESETS[0] as DevicePreset
    }, [deviceId])

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
        initSyncProgress,
        registerSaveHandler,
        undoLastChange,
        redoLastChange,
        setMultiSelectElements,
        clearSelection,
        isInteractMode
    } = useDesignModeContext()

    const isEnabledRef = useRef(isEnabled)
    useEffect(() => {
        isEnabledRef.current = isEnabled
    }, [isEnabled])

    const isInteractModeRef = useRef(isInteractMode)
    useEffect(() => {
        isInteractModeRef.current = isInteractMode
    }, [isInteractMode])

    const selectedElementRef = useRef<ElementInfo | null>(selectedElement)
    useEffect(() => {
        selectedElementRef.current = selectedElement
    }, [selectedElement])

    const clearSelectionRef = useRef(clearSelection)
    useEffect(() => {
        clearSelectionRef.current = clearSelection
    }, [clearSelection])

    // Clear selection whenever the user clicks anywhere outside the iframe.
    // (Clicks inside the iframe don't bubble to the parent document.)
    // We track whether a Radix Select is open so we can suppress deselection
    // when the user clicks to dismiss a dropdown. We use a ref + MutationObserver
    // because Radix may remove the select content from the DOM before our
    // pointerdown handler checks for it.
    const radixSelectOpenRef = useRef(false)
    useEffect(() => {
        const updateFlag = () => {
            radixSelectOpenRef.current =
                document.querySelector('[data-radix-select-viewport]') !==
                null ||
                document.querySelector('[data-slot="select-content"]') !== null
        }
        updateFlag()
        const observer = new MutationObserver(updateFlag)
        observer.observe(document.body, { childList: true, subtree: true })
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        const handlePointerDown = (event: PointerEvent) => {
            if (!isEnabledRef.current) return
            if (!selectedElementRef.current) return
            if (event.defaultPrevented) return
            if (event.button !== 0) return

            const target = event.target
            if (!(target instanceof Element)) return
            if (target.closest('[data-design-mode-preserve-selection]')) return
            // Preserve selection when interacting with Radix UI portals (dropdowns, selects, dialogs, etc.)
            if (target.closest('[data-radix-popper-content-wrapper]')) return
            if (target.closest('[data-radix-portal]')) return
            if (target.closest('[data-radix-select-viewport]')) return
            // Radix Select uses a DismissableLayer that can place elements outside portals
            if (target.closest('[data-radix-dismissable-layer]')) return
            // Catch-all: any element inside a Radix-managed Select content
            if (target.closest('[data-slot="select-content"]')) return
            // When a Radix Select dropdown is open, clicks anywhere (including on
            // scroll-lock overlays or focus guards that live outside portals) are
            // intended to close the dropdown, not to deselect the design element.
            if (radixSelectOpenRef.current) return

            clearSelectionRef.current()
        }

        document.addEventListener('pointerdown', handlePointerDown, true)
        return () => {
            document.removeEventListener('pointerdown', handlePointerDown, true)
        }
    }, [])

    const srcRef = useRef(src)
    useEffect(() => {
        srcRef.current = src
    }, [src])

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

    // Calculate device dimensions
    const deviceDimensions = useMemo(() => {
        if (selectedDevice.id === 'responsive') {
            return { width: 0, height: 0 }
        }
        return { width: selectedDevice.width, height: selectedDevice.height }
    }, [selectedDevice])

    const [proxiedHtml, setProxiedHtml] = useState<string | null>(null)
    const [isProxyLoading, setIsProxyLoading] = useState(false)
    const [trackedUrl, setTrackedUrl] = useState<string>(src)

    // Track URLs reported during interact mode so we can re-proxy on exit.
    const deferredUrlRef = useRef<string | null>(null)

    // Reset tracked URL when the base src changes (e.g. new session/project)
    useEffect(() => {
        setTrackedUrl(src)
    }, [src])

    const isProxyMode = Boolean(isEnabled && sessionId)
    const iframeSrc = isProxyMode ? 'about:blank' : src
    const iframeSrcDoc = isProxyMode ? (proxiedHtml ?? undefined) : undefined
    // Note: allow-same-origin is needed for CSS/fonts to load via CORS in proxy mode.
    // This gives the iframe the parent's origin, which is acceptable since users
    // are previewing their own project code, not untrusted content.
    const iframeSandbox =
        'allow-scripts allow-same-origin allow-forms allow-popups allow-presentation'

    /**
     * Load proxied HTML via authenticated XHR and inject into the iframe via srcDoc.
     * This avoids putting bearer tokens in the iframe URL and keeps the preview origin isolated.
     */
    useEffect(() => {
        let cancelled = false

        if (!isProxyMode || !sessionId) {
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
                const response = await axiosInstance.get('/design-mode/proxy', {
                    params: { session_id: sessionId, url: trackedUrl },
                    responseType: 'text'
                })
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
                    '[DesignModeWrapper] Failed to load design mode proxy HTML:',
                    err
                )
                if (cancelled) return
                setIsProxyLoading(false)
                setProxiedHtml(null)

                // Extract error detail from response
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
                    } else if (
                        responseData &&
                        typeof responseData === 'object' &&
                        'detail' in responseData &&
                        typeof (responseData as { detail: unknown }).detail ===
                        'string'
                    ) {
                        detail = (responseData as { detail: string }).detail
                    }
                }

                setError(detail || t('designMode.errors.failedToLoadPreview'))
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [isProxyMode, sessionId, trackedUrl, setIsReady, setError])

    /**
     * Load persisted design-mode changes from DB and hydrate the UI state.
     */
    useEffect(() => {
        if (!sessionId) {
            setIsDesignStateLoaded(true)
            setPersistedChanges([])
            return
        }

        let cancelled = false
        setIsDesignStateLoaded(false)

        const load = async () => {
            try {
                const response = await axiosInstance.get('/design-mode/state', {
                    params: { session_id: sessionId }
                })
                const serverChanges = Array.isArray(response?.data?.changes)
                    ? (response.data.changes as DesignChange[])
                    : []
                const serverRedoChanges = Array.isArray(
                    response?.data?.redo_changes
                )
                    ? (response.data.redo_changes as DesignChange[])
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
                    '[DesignModeWrapper] Failed to load persisted design state:',
                    err
                )
                if (cancelled) return
                setPersistedChanges([])
                setIsDesignStateLoaded(true)
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [sessionId, replaceChanges, mergeChanges, replaceRedoChanges])

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
     * Send a message to the iframe
     */
    const sendMessage = useCallback((type: string, payload?: unknown) => {
        if (!iframeRef.current?.contentWindow) {
            console.warn('[DesignModeWrapper] No iframe window')
            return
        }
        iframeRef.current.contentWindow.postMessage({ type, payload }, '*')
    }, [])

    // Keep a ref to sendMessage to avoid stale closures in registered handlers
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
                    '[DesignModeWrapper] requestDocumentSnapshot: no iframe window'
                )
                return null
            }
            if (!isEnabled || !isReady) {
                console.warn(
                    '[DesignModeWrapper] requestDocumentSnapshot: not ready',
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
                            '[DesignModeWrapper] Document snapshot request timed out',
                            requestId
                        )
                        snapshotRequestsRef.current.delete(requestId)
                        resolve(null)
                    }, 2500)

                    snapshotRequestsRef.current.set(requestId, {
                        resolve,
                        timeoutId
                    })

                    console.log(
                        '[DesignModeWrapper] Requesting document snapshot',
                        requestId,
                        options
                    )
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
     * Handle messages from the iframe runtime
     */
    useEffect(() => {
        const handleIframeMessage = (event: MessageEvent) => {
            // Only handle messages from our iframe
            if (!iframeRef.current?.contentWindow) return
            if (event.source !== iframeRef.current.contentWindow) return

            const { type, payload } = event.data || {}

            switch (type) {
                case 'DESIGN_MODE_READY':
                    setIsReady(true)
                    setError(null)
                    if (isEnabledRef.current && !isInteractModeRef.current) {
                        // Ensure the runtime is enabled even if `isReady` didn't transition
                        // (e.g. iframe reload/remount).
                        // Skip if in interact mode — the user is browsing the iframe freely.
                        sendMessageRef.current('DESIGN_MODE_ENABLE')
                    }
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

                case 'DESIGN_MODE_OP_RESULT': {
                    const op =
                        payload && typeof payload.op === 'string'
                            ? (payload.op as string)
                            : 'unknown'
                    const designId =
                        payload && typeof payload.designId === 'string'
                            ? (payload.designId as string)
                            : 'unknown'
                    const ok =
                        payload && typeof payload.ok === 'boolean'
                            ? (payload.ok as boolean)
                            : false
                    if (!ok) {
                        console.warn(
                            `[DesignModeWrapper] Runtime op failed: op=${op} designId=${designId}`,
                            payload
                        )
                    } else {
                        console.debug(
                            `[DesignModeWrapper] Runtime op ok: op=${op} designId=${designId}`
                        )
                    }
                    break
                }

                case 'DESIGN_MODE_UNDO_REQUEST':
                    undoLastChange()
                    break

                case 'DESIGN_MODE_REDO_REQUEST':
                    redoLastChange()
                    break

                case 'DESIGN_MODE_MULTI_SELECT_CHANGE': {
                    const selected = (payload as { selected?: ElementInfo[] })
                        ?.selected
                    if (Array.isArray(selected)) {
                        setMultiSelectElements(selected)
                    }
                    break
                }

                case 'IFRAME_URL_CHANGE':
                case 'navigation':
                case 'url-change':
                case 'route-change':
                case 'NAVIGATION':
                case 'URL_CHANGE':
                case 'ROUTE_CHANGE': {
                    // Handle URL change reports from the iframe's navigation reporter.
                    // The AI may generate the reporter with different message types —
                    // we handle all common variants.
                    const data = event.data || {}
                    const reportedUrl =
                        (payload &&
                            typeof payload === 'object' &&
                            'url' in payload &&
                            typeof (payload as { url: unknown }).url ===
                            'string' &&
                            (payload as { url: string }).url) ||
                        (typeof data.url === 'string' && data.url) ||
                        null
                    if (
                        reportedUrl &&
                        reportedUrl !== 'about:srcdoc' &&
                        reportedUrl !== 'about:blank'
                    ) {
                        // Validate the reported URL has the same origin as
                        // the sandbox src to prevent SSRF via crafted messages.
                        try {
                            const srcOrigin = new URL(srcRef.current).origin
                            const reportedOrigin = new URL(reportedUrl).origin
                            if (reportedOrigin !== srcOrigin) break

                            if (isInteractModeRef.current) {
                                // Defer URL update until interact mode exits
                                // to avoid re-fetching proxy while user navigates.
                                deferredUrlRef.current = reportedUrl
                            } else if (!isEnabledRef.current) {
                                setTrackedUrl(reportedUrl)
                            }
                        } catch {
                            // Ignore invalid URLs
                        }
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
                            '[DesignModeWrapper] Received snapshot without requestId'
                        )
                        break
                    }
                    const pending = snapshotRequestsRef.current.get(requestId)
                    if (!pending) {
                        console.warn(
                            '[DesignModeWrapper] No pending snapshot request for',
                            requestId
                        )
                        break
                    }
                    clearTimeout(pending.timeoutId)
                    snapshotRequestsRef.current.delete(requestId)

                    const snapshot =
                        payload && typeof payload.snapshot === 'object'
                            ? (payload.snapshot as DesignModeDocumentSnapshot)
                            : null
                    console.log(
                        '[DesignModeWrapper] Received document snapshot',
                        requestId,
                        {
                            hasSnapshot: !!snapshot,
                            nodeCount: snapshot?.nodes?.length || 0
                        }
                    )
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
        redoLastChange,
        setMultiSelectElements
    ])

    /**
     * When enabled and ready, send enable message (unless in interact mode)
     */
    useEffect(() => {
        if (isEnabled && isReady && !isInteractMode) {
            sendMessage('DESIGN_MODE_ENABLE')
        }
    }, [isEnabled, isReady, isInteractMode, sendMessage])

    /**
     * When exiting interact mode, apply any deferred URL the user navigated to
     * so the proxy re-fetches the new page with the design-mode runtime.
     */
    useEffect(() => {
        if (!isInteractMode && deferredUrlRef.current) {
            setTrackedUrl(deferredUrlRef.current)
            deferredUrlRef.current = null
        }
    }, [isInteractMode])

    /**
     * Apply persisted changes to the freshly loaded iframe (design mode proxy).
     * This is best-effort and does not block UI; changes in the iframe should remain instant.
     */
    const hasAppliedPersistedChangesRef = useRef(false)
    useEffect(() => {
        hasAppliedPersistedChangesRef.current = false
    }, [iframeSrc, iframeSrcDoc])

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
            if (change.type === 'move') {
                const toValue = change.value?.to || ''
                if (!toValue) {
                    return
                }
                if (
                    toValue === 'only' ||
                    toValue.startsWith('before:') ||
                    toValue.startsWith('after:')
                ) {
                    sendMessage('DESIGN_MODE_MOVE_ELEMENT', {
                        designId: change.designId,
                        anchor: toValue,
                        skipTracking: true
                    })
                    return
                }

                // Backward compatibility: earlier move changes used raw swap targets.
                sendMessage('DESIGN_MODE_SWAP_ELEMENTS', {
                    designId: change.designId,
                    targetDesignId: toValue,
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
                    text: change.value?.to || '',
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
                return
            }

            if (change.type === 'delete') {
                sendMessage('DESIGN_MODE_DELETE_ELEMENT', {
                    designId: change.designId,
                    xpath: change.elementContext?.xpath,
                    skipTracking: true
                })
                return
            }

            if (change.type === 'style') {
                sendMessage('DESIGN_MODE_SET_STYLE', {
                    designId: change.designId,
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
     * Send disable when design mode is turned off
     */
    useEffect(() => {
        if (!isEnabled) {
            sendMessage('DESIGN_MODE_DISABLE')
        }
    }, [isEnabled, sendMessage])

    /**
     * Timeout for runtime not responding
     */
    useEffect(() => {
        if (!isEnabled) return
        if (isProxyLoading) return
        if (isProxyMode && !proxiedHtml) return

        const timeout = setTimeout(() => {
            if (isEnabled && !isReady) {
                setError(t('designMode.errors.runtimeNotResponding'))
            }
        }, 5000)

        return () => clearTimeout(timeout)
    }, [isEnabled, isReady, isProxyLoading, isProxyMode, proxiedHtml, setError])

    /**
     * Register style handlers with context
     */
    useEffect(() => {
        registerStyleHandlers({
            setStyle: (property: string, value: string) => {
                if (!selectedElement) return
                sendMessage('DESIGN_MODE_SET_STYLE', {
                    designId: selectedElement.designId,
                    property,
                    value
                })
            },
            setText: (text: string) => {
                if (!selectedElement) return
                sendMessage('DESIGN_MODE_SET_TEXT', {
                    designId: selectedElement.designId,
                    text
                })
            },
            resetStyles: () => {
                if (!selectedElement) return
                TRACKED_PROPERTIES.forEach((prop) => {
                    sendMessage('DESIGN_MODE_SET_STYLE', {
                        designId: selectedElement.designId,
                        property: prop,
                        value: ''
                    })
                })
            },
            revertChange: (change: DesignChange) => {
                // Revert a specific change by setting the property back to original value
                // skipTracking: true prevents this from being tracked as a new change
                // Use ref to ensure we always have the latest sendMessage
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
                            anchor: fromValue,
                            skipTracking: true
                        })
                        return
                    }

                    // Backward compatibility: earlier move changes used raw swap targets.
                    sendMessageRef.current('DESIGN_MODE_SWAP_ELEMENTS', {
                        designId: change.designId,
                        targetDesignId: toValue,
                        skipTracking: true
                    })
                    return
                }

                if (change.type === 'text') {
                    // For text changes, use SET_TEXT message
                    sendMessageRef.current('DESIGN_MODE_SET_TEXT', {
                        designId: change.designId,
                        text: change.value.from || '',
                        skipTracking: true
                    })
                    return
                }

                if (change.type === 'delete') {
                    sendMessageRef.current('DESIGN_MODE_RESTORE_ELEMENT', {
                        designId: change.designId,
                        xpath: change.elementContext?.xpath,
                        skipTracking: true
                    })
                    return
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
                        iconName,
                        svgInner,
                        skipTracking: true
                    })
                    return
                }

                if (change.type === 'style') {
                    // For style changes, use SET_STYLE message
                    sendMessageRef.current('DESIGN_MODE_SET_STYLE', {
                        designId: change.designId,
                        property: change.property,
                        value: change.value.from || '',
                        skipTracking: true
                    })
                }
            },
            highlightElement: (designId: string) => {
                // Send message to highlight element in iframe
                // Use ref to ensure we always have the latest sendMessage
                sendMessageRef.current('DESIGN_MODE_HIGHLIGHT_ELEMENT', {
                    designId
                })
            },
            setElementLoading: (designId: string, isLoading: boolean) => {
                const xpath =
                    selectedElement && selectedElement.designId === designId
                        ? selectedElement.xpath
                        : undefined
                sendMessageRef.current('DESIGN_MODE_SET_ELEMENT_LOADING', {
                    designId,
                    isLoading,
                    xpath
                })
            },
            sendMessage: (type: DesignModeMessageType, payload?: unknown) => {
                sendMessageRef.current(type, payload)
            },
            requestDocumentSnapshot: requestDocumentSnapshot
        })
    }, [selectedElement, registerStyleHandlers, requestDocumentSnapshot])

    /**
     * Persist pending design changes to DB (debounced) so refresh/session re-entry restores them.
     * Debounce keeps iframe updates instant and avoids spamming the backend on sliders/drags.
     */
    const persistTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const persistState = useCallback(
        async (changes: DesignChange[]) => {
            if (!sessionId) return
            try {
                await axiosInstance.post('/design-mode/state', {
                    session_id: sessionId,
                    changes,
                    redo_changes: redoChangesRef.current
                })
            } catch (err) {
                console.error(
                    '[DesignModeWrapper] Failed to persist design state:',
                    err
                )
            }
        },
        [sessionId]
    )

    useEffect(() => {
        // Prevent wiping server state with an initial empty list before the GET completes.
        if (!isDesignStateLoaded) return
        if (!sessionId) return
        if (isSaving) return

        if (persistTimeoutRef.current) {
            clearTimeout(persistTimeoutRef.current)
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
        sessionId,
        pendingChanges,
        redoChanges,
        persistState,
        isSaving
    ])

    // Flush pending debounced save on unmount/session change (best-effort).
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

    const handleSave = useCallback(
        async (changesOverride?: DesignChange[]) => {
            if (!sessionId) {
                toast.error(t('designMode.toasts.missingSessionId'))
                return
            }
            if (isSaving) return

            const changesToSync = Array.isArray(changesOverride)
                ? changesOverride
                : pendingChanges
            if (changesToSync.length === 0) return

            if (persistTimeoutRef.current) {
                clearTimeout(persistTimeoutRef.current)
                persistTimeoutRef.current = null
            }

            const selectedKeySet = Array.isArray(changesOverride)
                ? new Set(changesToSync.map(buildDesignChangeKeyWithTimestamp))
                : null
            const unselectedChanges = selectedKeySet
                ? pendingChanges.filter(
                    (change) =>
                        !selectedKeySet.has(
                            buildDesignChangeKeyWithTimestamp(change)
                        )
                )
                : []

            // Initialize progress state before sync starts so UI shows 0/N immediately
            initSyncProgress(changesToSync.length)
            setIsSaving(true)

            // Allow React to render the initial progress state before starting the sync
            await new Promise((resolve) => setTimeout(resolve, 0))

            try {
                // Ensure the latest local changes are flushed to DB so sync uses the current state.
                if (changesToSync.length > 0) {
                    await axiosInstance.post('/design-mode/state', {
                        session_id: sessionId,
                        changes: changesToSync,
                        redo_changes: redoChangesRef.current
                    })
                }

                const response = await axiosInstance.post(
                    '/design-mode/sync-state',
                    {
                        session_id: sessionId
                    }
                )

                const applied =
                    response?.data && typeof response.data.applied === 'number'
                        ? response.data.applied
                        : undefined

                const remainingChanges = Array.isArray(
                    response?.data?.remaining_changes
                )
                    ? (response.data.remaining_changes as DesignChange[])
                    : []
                const mergedRemaining =
                    selectedKeySet !== null
                        ? [...unselectedChanges, ...remainingChanges]
                        : remainingChanges

                replaceChanges(mergedRemaining)

                try {
                    window.dispatchEvent(
                        new CustomEvent('design-mode-state-updated', {
                            detail: {
                                session_id: sessionId,
                                changes: mergedRemaining,
                                redo_changes: redoChangesRef.current
                            }
                        })
                    )
                } catch (e) {
                    console.warn(
                        'Failed to dispatch design-mode-state-updated event',
                        e
                    )
                }

                if (selectedKeySet !== null) {
                    try {
                        await axiosInstance.post('/design-mode/state', {
                            session_id: sessionId,
                            changes: mergedRemaining,
                            redo_changes: redoChangesRef.current
                        })
                    } catch (e) {
                        console.warn(
                            '[DesignModeWrapper] Failed to restore design state after partial sync',
                            e
                        )
                    }
                }

                const summary =
                    typeof response?.data?.summary === 'string'
                        ? (response.data.summary as string)
                        : applied !== undefined
                            ? t('designMode.messages.syncedDesignChanges', {
                                count: applied
                            })
                            : t('designMode.messages.syncedDesignChangesDefault')

                const isSyncSuccess = response?.data?.success === true
                const total =
                    response?.data && typeof response.data.total === 'number'
                        ? (response.data.total as number)
                        : undefined
                const remaining =
                    response?.data &&
                        typeof response.data.remaining === 'number'
                        ? (response.data.remaining as number)
                        : undefined

                const eventId =
                    typeof response?.data?.event_id === 'string'
                        ? (response.data.event_id as string)
                        : `${Date.now()}-design-sync`

                dispatch(
                    addMessage({
                        id: eventId,
                        role: 'assistant',
                        content: summary,
                        timestamp: Date.now()
                    })
                )

                dispatch(setBuildMode(BUILD_MODE.BUILD))

                if (isSyncSuccess) {
                    toast.success(
                        applied !== undefined
                            ? t('designMode.toasts.syncSuccessApplied', {
                                applied
                            })
                            : t('designMode.toasts.syncSuccess')
                    )
                } else if (
                    applied !== undefined &&
                    total !== undefined &&
                    applied > 0 &&
                    remaining !== undefined &&
                    remaining > 0
                ) {
                    toast.message(
                        t('designMode.toasts.partialSync', { applied, total })
                    )
                } else {
                    toast.error(t('designMode.toasts.syncFailed'))
                }
            } catch (e) {
                console.error('[DesignModeWrapper] Save error:', e)
                toast.error(t('designMode.toasts.saveFailed'))
            } finally {
                setIsSaving(false)
            }
        },
        [
            sessionId,
            pendingChanges,
            isSaving,
            initSyncProgress,
            setIsSaving,
            replaceChanges,
            dispatch,
            t
        ]
    )

    useEffect(() => {
        registerSaveHandler(handleSave)
    }, [registerSaveHandler, handleSave])

    return (
        <div
            className={cn(
                'relative w-full h-full flex flex-col overflow-hidden',
                className
            )}
        >
            <IframePreview
                iframeRef={iframeRef}
                iframeSrc={iframeSrc}
                iframeSrcDoc={iframeSrcDoc}
                iframeSandbox={iframeSandbox}
                iframeClassName={iframeClassName}
                isEnabled={isEnabled}
                isInteractMode={isInteractMode}
                isSaving={isSaving}
                syncProgress={syncProgress}
                selectedDevice={selectedDevice}
                deviceDimensions={deviceDimensions}
            />
            <ErrorOverlay isEnabled={isEnabled} error={error} />
        </div>
    )
}
