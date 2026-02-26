/**
 * Storybook Edit Wrapper Component
 *
 * Wraps an iframe that loads storybook page HTML with design-mode runtime.
 * Handles communication with the iframe runtime to track changes.
 */

import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import { Loader2, AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import axiosInstance from '@/lib/axios'
import {
    useStorybookEdit,
    type DesignChange
} from '@/contexts/storybook-edit-context'
import type {
    ElementInfo,
    DesignModeMessageType
} from '@/components/design-mode/types'

type DesignModeSetStylePayload = {
    designId: string
    property: string
    value: string | null
    skipTracking?: boolean
}

type DesignModeSetTextPayload = {
    designId: string
    text: string | null
    skipTracking?: boolean
}

type DesignModeSetAttributePayload = {
    designId: string
    attribute: string
    value: string | null
    xpath?: string
    skipTracking?: boolean
}

interface StorybookEditWrapperProps {
    storybookId: string
    pageNumber: number
    className?: string
    onElementSelect?: (element: ElementInfo | null) => void
    onElementDoubleClick?: (element: ElementInfo) => void
    onReady?: () => void
    onUndoRequest?: () => void
    onRedoRequest?: () => void
}

// Default page dimensions (will be overridden by actual content)
const DEFAULT_PAGE_WIDTH = 800
const DEFAULT_PAGE_HEIGHT = 1200

function extractDetailFromData(data: unknown): string | null {
    if (!data || typeof data !== 'object' || !('detail' in data)) {
        return null
    }
    const detail = (data as { detail: unknown }).detail
    return typeof detail === 'string' ? detail : null
}

function extractErrorDetail(err: unknown, fallback: string): string {
    if (!err || typeof err !== 'object' || !('response' in err)) {
        return fallback
    }

    const response = (err as { response?: { data?: unknown } }).response
    const responseData = response?.data

    // Try to parse JSON string response
    if (typeof responseData === 'string' && responseData) {
        try {
            const parsed = JSON.parse(responseData) as unknown
            const detail = extractDetailFromData(parsed)
            if (detail) return detail
        } catch {
            // JSON parse failed, continue
        }
    }

    // Try to extract from object response
    const detail = extractDetailFromData(responseData)
    if (detail) return detail

    return fallback
}

function getElementContextXpath(change: DesignChange): string | undefined {
    const elementContext = change.elementContext
    if (!elementContext || typeof elementContext !== 'object') return undefined
    const xpath = (elementContext as { xpath?: unknown }).xpath
    return typeof xpath === 'string' ? xpath : undefined
}

export function StorybookEditWrapper({
    storybookId,
    pageNumber,
    className,
    onElementSelect,
    onElementDoubleClick,
    onReady,
    onUndoRequest,
    onRedoRequest
}: StorybookEditWrapperProps) {
    const { addChange, getPageChanges } = useStorybookEdit()
    const { t } = useTranslation()

    const iframeRef = useRef<HTMLIFrameElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [isReady, setIsReady] = useState(false)
    const [proxiedHtml, setProxiedHtml] = useState<string | null>(null)
    const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
    const [contentSize, setContentSize] = useState({
        width: DEFAULT_PAGE_WIDTH,
        height: DEFAULT_PAGE_HEIGHT
    })

    // Calculate scale to fit content in container with centering offsets
    const { scale, offsetX, offsetY } = useMemo(() => {
        const hasValidDimensions =
            containerSize.width > 0 &&
            containerSize.height > 0 &&
            contentSize.width > 0 &&
            contentSize.height > 0

        if (!hasValidDimensions) {
            return { scale: 1, offsetX: 0, offsetY: 0 }
        }

        const padding = 4
        const availableWidth = containerSize.width - padding * 2
        const availableHeight = containerSize.height - padding * 2

        // Scale down to fit, but never scale up
        const fitScale = Math.min(
            availableWidth / contentSize.width,
            availableHeight / contentSize.height,
            1
        )

        // Center the scaled content
        return {
            scale: fitScale,
            offsetX: (containerSize.width - contentSize.width * fitScale) / 2,
            offsetY: (containerSize.height - contentSize.height * fitScale) / 2
        }
    }, [containerSize, contentSize])

    // Update container size on resize
    useEffect(() => {
        const updateSize = () => {
            if (containerRef.current) {
                setContainerSize({
                    width: containerRef.current.clientWidth,
                    height: containerRef.current.clientHeight
                })
            }
        }

        updateSize()
        window.addEventListener('resize', updateSize)

        // Also observe container resize
        const resizeObserver = new ResizeObserver(updateSize)
        if (containerRef.current) {
            resizeObserver.observe(containerRef.current)
        }

        return () => {
            window.removeEventListener('resize', updateSize)
            resizeObserver.disconnect()
        }
    }, [])

    // Load the proxied HTML with design-mode runtime
    useEffect(() => {
        let cancelled = false

        setIsLoading(true)
        setError(null)
        setIsReady(false)
        setProxiedHtml(null)

        const load = async () => {
            try {
                const response = await axiosInstance.get(
                    `/storybooks/${storybookId}/edit/proxy`,
                    {
                        params: {
                            page_number: pageNumber
                        },
                        responseType: 'text'
                    }
                )

                const html =
                    typeof response.data === 'string' ? response.data : null
                if (!html || !html.trim()) {
                    throw new Error('Empty proxy response')
                }

                // Try to extract content dimensions from HTML
                const widthMatch = html.match(/width:\s*(\d+)px/)
                const heightMatch = html.match(/height:\s*(\d+)px/)
                if (widthMatch && heightMatch) {
                    setContentSize({
                        width: parseInt(widthMatch[1], 10),
                        height: parseInt(heightMatch[1], 10)
                    })
                }

                if (cancelled) return
                setProxiedHtml(html)
                setIsLoading(false)
            } catch (err) {
                console.error(
                    '[StorybookEditWrapper] Failed to load page HTML:',
                    err
                )
                if (cancelled) return
                setIsLoading(false)
                setProxiedHtml(null)
                setError(
                    extractErrorDetail(
                        err,
                        t('storybook.editWrapper.errors.loadFailed')
                    )
                )
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [storybookId, pageNumber, t])

    // Send message to iframe
    const sendMessage = useCallback(
        (type: DesignModeMessageType, payload?: unknown) => {
            if (!iframeRef.current?.contentWindow) {
                console.warn('[StorybookEditWrapper] No iframe window')
                return
            }
            iframeRef.current.contentWindow.postMessage({ type, payload }, '*')
        },
        []
    )

    // Handle messages from the iframe runtime
    useEffect(() => {
        const handleMessage = (event: MessageEvent) => {
            const iframeWindow = iframeRef.current?.contentWindow
            if (!iframeWindow || event.source !== iframeWindow) return

            const data = event.data as
                | { type?: string; payload?: unknown }
                | undefined
            if (!data || typeof data !== 'object' || !data.type) return

            switch (data.type) {
                case 'DESIGN_MODE_READY': {
                    console.log('[StorybookEditWrapper] Runtime ready')
                    setIsReady(true)
                    // Enable design mode in the iframe
                    sendMessage('DESIGN_MODE_ENABLE')

                    // Apply any existing changes for this page (e.g., when returning to a previously edited page)
                    const existingChanges = getPageChanges(pageNumber)
                    if (existingChanges.length > 0) {
                        console.log(
                            `[StorybookEditWrapper] Applying ${existingChanges.length} existing changes to page ${pageNumber}`
                        )
                        existingChanges.forEach((change) => {
                            if (change.type === 'style') {
                                const payload: DesignModeSetStylePayload = {
                                    designId: change.designId,
                                    property: change.property,
                                    value: change.value.to,
                                    skipTracking: true
                                }
                                sendMessage('DESIGN_MODE_SET_STYLE', payload)
                            } else if (change.type === 'text') {
                                const payload: DesignModeSetTextPayload = {
                                    designId: change.designId,
                                    text: change.value.to,
                                    skipTracking: true
                                }
                                sendMessage('DESIGN_MODE_SET_TEXT', payload)
                            } else if (change.type === 'attribute') {
                                if (change.property === 'icon') {
                                    const raw = change.value?.to || ''
                                    let iconName = ''
                                    let svgInner = ''
                                    try {
                                        const parsed = JSON.parse(raw) as
                                            | {
                                                  name?: unknown
                                                  svg?: unknown
                                              }
                                            | undefined
                                        iconName =
                                            parsed &&
                                            typeof parsed.name === 'string'
                                                ? parsed.name
                                                : ''
                                        svgInner =
                                            parsed &&
                                            typeof parsed.svg === 'string'
                                                ? parsed.svg
                                                : ''
                                    } catch {
                                        svgInner = raw
                                    }

                                    if (svgInner) {
                                        sendMessage('DESIGN_MODE_SET_ICON', {
                                            designId: change.designId,
                                            iconName,
                                            svgInner,
                                            xpath: getElementContextXpath(
                                                change
                                            ),
                                            skipTracking: true
                                        })
                                    }
                                    return
                                }

                                const payload: DesignModeSetAttributePayload = {
                                    designId: change.designId,
                                    attribute: change.property,
                                    value: change.value.to,
                                    xpath: getElementContextXpath(change),
                                    skipTracking: true
                                }
                                sendMessage(
                                    'DESIGN_MODE_SET_ATTRIBUTE',
                                    payload
                                )
                            }
                        })
                    }

                    onReady?.()
                    break
                }

                case 'DESIGN_MODE_ELEMENT_SELECT':
                    onElementSelect?.(data.payload as ElementInfo | null)
                    break

                case 'DESIGN_MODE_ELEMENT_DOUBLE_CLICK':
                    onElementDoubleClick?.(data.payload as ElementInfo)
                    break

                case 'DESIGN_MODE_CHANGE': {
                    const change = data.payload as DesignChange | undefined
                    if (change) {
                        addChange(pageNumber, change)
                    }
                    break
                }

                case 'DESIGN_MODE_CONTENT_SIZE': {
                    const size = data.payload as
                        | { width?: number; height?: number }
                        | undefined
                    if (size?.width && size?.height) {
                        setContentSize({
                            width: size.width,
                            height: size.height
                        })
                    }
                    break
                }

                case 'DESIGN_MODE_UNDO_REQUEST':
                    onUndoRequest?.()
                    break

                case 'DESIGN_MODE_REDO_REQUEST':
                    onRedoRequest?.()
                    break
            }
        }

        window.addEventListener('message', handleMessage)
        return () => {
            window.removeEventListener('message', handleMessage)
        }
    }, [
        pageNumber,
        addChange,
        getPageChanges,
        sendMessage,
        onElementSelect,
        onElementDoubleClick,
        onReady,
        onUndoRequest,
        onRedoRequest
    ])

    // Loading state
    if (isLoading) {
        return (
            <div
                ref={containerRef}
                className={cn(
                    'flex items-center justify-center bg-background',
                    className
                )}
            >
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <span className="text-sm">
                        {t('storybook.editWrapper.loading')}
                    </span>
                </div>
            </div>
        )
    }

    // Error state
    if (error) {
        return (
            <div
                ref={containerRef}
                className={cn(
                    'flex items-center justify-center bg-background',
                    className
                )}
            >
                <div className="flex flex-col items-center gap-3 text-destructive">
                    <AlertTriangle className="h-8 w-8" />
                    <span className="text-sm text-center max-w-md">
                        {error}
                    </span>
                </div>
            </div>
        )
    }

    return (
        <div
            ref={containerRef}
            className={cn('relative overflow-hidden', className)}
        >
            {/* Status indicator */}
            {!isReady && proxiedHtml && (
                <div className="absolute top-2 left-2 z-10 bg-background/80 backdrop-blur-sm px-2 py-1 rounded text-xs text-muted-foreground flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>{t('storybook.editWrapper.initializing')}</span>
                </div>
            )}

            {/* Scaled iframe container */}
            <div
                className="absolute"
                style={{
                    width: contentSize.width,
                    height: contentSize.height,
                    transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
                    transformOrigin: 'top left'
                }}
            >
                {/* The iframe with page HTML and design-mode runtime */}
                <iframe
                    ref={iframeRef}
                    title={t('storybook.editWrapper.iframeTitle', {
                        page: pageNumber
                    })}
                    className="border-0 bg-white"
                    style={{
                        width: contentSize.width,
                        height: contentSize.height
                    }}
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-presentation"
                    srcDoc={proxiedHtml ?? undefined}
                />
            </div>
        </div>
    )
}

export type { StorybookEditWrapperProps }
