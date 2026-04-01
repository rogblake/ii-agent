/**
 * useDesignMode Hook
 *
 * Manages the design mode state and communication with the iframe runtime.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import axiosInstance from '@/lib/axios'
import type { ElementInfo, DesignChange, DesignModeState } from './types'

export interface UseDesignModeOptions {
    /** The direct sandbox URL */
    sandboxUrl: string
    /** Session ID for API calls */
    sessionId?: string
    /** Called when an element is selected */
    onElementSelect?: (element: ElementInfo | null) => void
    /** Called when user double-clicks (for AI chat) */
    onElementDoubleClick?: (element: ElementInfo) => void
}

export interface UseDesignModeReturn {
    state: DesignModeState
    /** Reference to the iframe element */
    iframeRef: React.RefObject<HTMLIFrameElement | null>
    /** The URL to use for the iframe src */
    iframeSrc: string
    /**
     * Optional HTML to inject via iframe srcDoc (proxy mode).
     * When present, the consumer should render the iframe with srcDoc={iframeSrcDoc}.
     */
    iframeSrcDoc?: string
    /**
     * Suggested iframe sandbox value (proxy mode uses an isolated origin).
     */
    iframeSandbox?: string
    /** Enable design mode */
    enable: () => void
    /** Disable design mode */
    disable: () => void
    /** Toggle design mode */
    toggle: () => void
    /** Set a style property on the selected element */
    setStyle: (property: string, value: string) => void
    /** Set text content on the selected element */
    setText: (text: string) => void
    /** Reset all styles on the selected element */
    resetStyles: () => void
    /** Get all pending changes */
    getPendingChanges: () => DesignChange[]
    /** Clear all pending changes */
    clearChanges: () => void
    /** Request sync of changes to source files */
    requestSync: () => void
}

const TRACKED_PROPERTIES = [
    'font-family',
    'font-size',
    'font-weight',
    'color',
    'background-color',
    'border-radius',
    'padding',
    'margin'
]

export function useDesignMode(
    options: UseDesignModeOptions
): UseDesignModeReturn {
    const { sandboxUrl, sessionId, onElementSelect, onElementDoubleClick } =
        options

    const iframeRef = useRef<HTMLIFrameElement>(null)
    const [proxiedHtml, setProxiedHtml] = useState<string | null>(null)
    const [isProxyLoading, setIsProxyLoading] = useState(false)

    const [state, setState] = useState<DesignModeState>({
        isEnabled: false,
        isReady: false,
        isProxyMode: false,
        selectedElement: null,
        hoveredElement: null,
        pendingChanges: [],
        error: null
    })

    const isProxyActive = Boolean(
        state.isEnabled && state.isProxyMode && sessionId
    )
    const iframeSrc = isProxyActive ? 'about:blank' : sandboxUrl
    const iframeSrcDoc = isProxyActive ? (proxiedHtml ?? undefined) : undefined
    // Note: allow-same-origin is needed for CSS/fonts to load via CORS in proxy mode.
    // This gives the iframe the parent's origin, which is acceptable since users
    // are previewing their own project code, not untrusted content.
    const iframeSandbox =
        'allow-scripts allow-same-origin allow-forms allow-popups allow-presentation'

    useEffect(() => {
        let cancelled = false

        if (!isProxyActive || !sessionId) {
            setIsProxyLoading(false)
            setProxiedHtml(null)
            return
        }

        setIsProxyLoading(true)
        setProxiedHtml(null)
        setState((prev) => ({ ...prev, isReady: false, error: null }))

        const load = async () => {
            try {
                const response = await axiosInstance.get('/v1/project/design/proxy', {
                    params: { session_id: sessionId, url: sandboxUrl },
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
                    '[useDesignMode] Failed to load design mode proxy HTML:',
                    err
                )
                if (cancelled) return
                setIsProxyLoading(false)
                setProxiedHtml(null)
                const responseData = (err as any)?.response?.data
                let detail: string | null = null
                if (typeof responseData === 'string' && responseData) {
                    try {
                        const parsed = JSON.parse(responseData)
                        if (
                            parsed &&
                            typeof parsed === 'object' &&
                            typeof (parsed as any).detail === 'string'
                        ) {
                            detail = (parsed as any).detail
                        }
                    } catch {
                        // ignore
                    }
                } else if (
                    responseData &&
                    typeof responseData === 'object' &&
                    typeof (responseData as any).detail === 'string'
                ) {
                    detail = (responseData as any).detail
                }

                setState((prev) => ({
                    ...prev,
                    error:
                        detail ||
                        'Failed to load design mode preview. Please refresh and try again.'
                }))
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [isProxyActive, sessionId, sandboxUrl])

    /**
     * Handle messages from the iframe runtime
     */
    const handleIframeMessage = useCallback(
        (event: MessageEvent) => {
            // Only handle messages from our iframe
            if (
                iframeRef.current &&
                event.source !== iframeRef.current.contentWindow
            ) {
                return
            }

            const { type, payload } = event.data || {}

            switch (type) {
                case 'DESIGN_MODE_READY':
                    setState((prev) => ({
                        ...prev,
                        isReady: true,
                        error: null
                    }))
                    console.log('[useDesignMode] Runtime ready')
                    break

                case 'DESIGN_MODE_ELEMENT_HOVER':
                    setState((prev) => ({
                        ...prev,
                        hoveredElement: payload as ElementInfo | null
                    }))
                    break

                case 'DESIGN_MODE_ELEMENT_SELECT':
                    setState((prev) => ({
                        ...prev,
                        selectedElement: payload as ElementInfo | null
                    }))
                    onElementSelect?.(payload as ElementInfo | null)
                    break

                case 'DESIGN_MODE_ELEMENT_DOUBLE_CLICK':
                    if (payload) {
                        onElementDoubleClick?.(payload as ElementInfo)
                    }
                    break

                case 'DESIGN_MODE_CHANGE':
                    const change = payload as DesignChange
                    setState((prev) => ({
                        ...prev,
                        pendingChanges: [...prev.pendingChanges, change]
                    }))
                    break

                default:
                    break
            }
        },
        [onElementSelect, onElementDoubleClick]
    )

    /**
     * Set up message listener
     */
    useEffect(() => {
        window.addEventListener('message', handleIframeMessage)
        return () => {
            window.removeEventListener('message', handleIframeMessage)
        }
    }, [handleIframeMessage])

    /**
     * Send a message to the iframe
     */
    const sendMessage = useCallback((type: string, payload?: unknown) => {
        if (!iframeRef.current?.contentWindow) {
            console.warn('[useDesignMode] No iframe window')
            return
        }
        iframeRef.current.contentWindow.postMessage({ type, payload }, '*')
    }, [])

    /**
     * Enable design mode
     */
    const enable = useCallback(() => {
        setState((prev) => ({
            ...prev,
            isEnabled: true,
            isProxyMode: true, // Switch to proxy mode to get injected runtime
            isReady: false,
            error: null
        }))
    }, [])

    /**
     * Disable design mode
     */
    const disable = useCallback(() => {
        sendMessage('DESIGN_MODE_DISABLE')
        setState((prev) => ({
            ...prev,
            isEnabled: false,
            isProxyMode: false, // Switch back to direct URL
            isReady: false,
            selectedElement: null,
            hoveredElement: null,
            error: null
        }))
    }, [sendMessage])

    /**
     * Toggle design mode
     */
    const toggle = useCallback(() => {
        if (state.isEnabled) {
            disable()
        } else {
            enable()
        }
    }, [state.isEnabled, enable, disable])

    /**
     * When iframe loads and runtime is ready, enable design mode
     */
    useEffect(() => {
        if (state.isEnabled && state.isReady) {
            sendMessage('DESIGN_MODE_ENABLE')
        }
    }, [state.isEnabled, state.isReady, sendMessage])

    useEffect(() => {
        if (!state.isEnabled) return
        if (isProxyLoading) return
        if (isProxyActive && !proxiedHtml) return

        const timeout = setTimeout(() => {
            setState((prev) => {
                if (prev.isEnabled && !prev.isReady) {
                    return {
                        ...prev,
                        error: 'Design mode runtime not responding. The preview may not support design mode.'
                    }
                }
                return prev
            })
        }, 5000)

        return () => clearTimeout(timeout)
    }, [
        state.isEnabled,
        state.isReady,
        isProxyLoading,
        isProxyActive,
        proxiedHtml
    ])

    /**
     * Set a style property on the selected element
     */
    const setStyle = useCallback(
        (property: string, value: string) => {
            if (!state.selectedElement) {
                console.warn('[useDesignMode] No element selected')
                return
            }

            sendMessage('DESIGN_MODE_SET_STYLE', {
                designId: state.selectedElement.designId,
                property,
                value
            })
        },
        [state.selectedElement, sendMessage]
    )

    /**
     * Set text content on the selected element
     */
    const setText = useCallback(
        (text: string) => {
            if (!state.selectedElement) {
                console.warn('[useDesignMode] No element selected')
                return
            }

            sendMessage('DESIGN_MODE_SET_TEXT', {
                designId: state.selectedElement.designId,
                text
            })
        },
        [state.selectedElement, sendMessage]
    )

    /**
     * Reset all tracked styles on the selected element
     */
    const resetStyles = useCallback(() => {
        if (!state.selectedElement) return

        TRACKED_PROPERTIES.forEach((prop) => {
            sendMessage('DESIGN_MODE_SET_STYLE', {
                designId: state.selectedElement!.designId,
                property: prop,
                value: '' // Empty value removes the style
            })
        })
    }, [state.selectedElement, sendMessage])

    /**
     * Get all pending changes
     */
    const getPendingChanges = useCallback(() => {
        return state.pendingChanges
    }, [state.pendingChanges])

    /**
     * Clear all pending changes
     */
    const clearChanges = useCallback(() => {
        sendMessage('DESIGN_MODE_CLEAR_CHANGES')
        setState((prev) => ({ ...prev, pendingChanges: [] }))
    }, [sendMessage])

    /**
     * Request sync of changes to source files
     */
    const requestSync = useCallback(() => {
        sendMessage('DESIGN_MODE_REQUEST_SYNC')
    }, [sendMessage])

    return {
        state,
        iframeRef,
        iframeSrc,
        iframeSrcDoc,
        iframeSandbox,
        enable,
        disable,
        toggle,
        setStyle,
        setText,
        resetStyles,
        getPendingChanges,
        clearChanges,
        requestSync
    }
}
