import { useMemo, useEffect, useRef, forwardRef } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { StorybookPageData } from '@/contexts/storybook-context'

// Declare KaTeX types for TypeScript
declare global {
    interface Window {
        renderMathInElement?: (element: HTMLElement, options: any) => void
        katexAutoRenderLoaded?: boolean
        katexRenderCache?: Set<string>
    }
}

// Load KaTeX scripts globally if not already loaded
const loadKatexScripts = (): Promise<void> => {
    if (window.katexAutoRenderLoaded) {
        return Promise.resolve()
    }

    return new Promise((resolve) => {
        // Check if scripts are already in the document
        const existingKatexScript = document.querySelector(
            'script[src*="katex.min.js"]'
        )
        const existingAutoRenderScript = document.querySelector(
            'script[src*="auto-render.min.js"]'
        )

        if (
            existingKatexScript &&
            existingAutoRenderScript &&
            window.renderMathInElement
        ) {
            window.katexAutoRenderLoaded = true
            resolve()
            return
        }

        // Load KaTeX CSS if not present
        if (!document.querySelector('link[href*="katex.min.css"]')) {
            const katexCss = document.createElement('link')
            katexCss.rel = 'stylesheet'
            katexCss.href =
                'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css'
            document.head.appendChild(katexCss)
        }

        // Load KaTeX JS
        const katexScript = document.createElement('script')
        katexScript.src =
            'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js'
        katexScript.integrity =
            'sha384-XjKyOOlGwcjNTAIQHIpgOno0Hl1YQqzUOEleOLALmuqehneUG+vnGctmUb0ZY0l8'
        katexScript.crossOrigin = 'anonymous'

        katexScript.onload = () => {
            // Load auto-render extension
            const autoRenderScript = document.createElement('script')
            autoRenderScript.src =
                'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js'
            autoRenderScript.integrity =
                'sha384-+VBxd3r6XgURycqtZ117nYw44OOcIax56Z4dCRWbxyPt0Koah1uHoK0o4+/RRE05'
            autoRenderScript.crossOrigin = 'anonymous'

            autoRenderScript.onload = () => {
                window.katexAutoRenderLoaded = true
                window.katexRenderCache = new Set()
                resolve()
            }

            document.head.appendChild(autoRenderScript)
        }

        document.head.appendChild(katexScript)
    })
}

// Render KaTeX in an element
const renderKatexInElement = async (
    element: HTMLElement,
    pageId: string,
    force = false
): Promise<void> => {
    if (!element) return

    // Skip if already rendered (unless forced)
    if (!force && window.katexRenderCache?.has(pageId)) return

    try {
        await loadKatexScripts()
        if (window.renderMathInElement) {
            window.renderMathInElement(element, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$', right: '$', display: false },
                    { left: '\\[', right: '\\]', display: true },
                    { left: '\\(', right: '\\)', display: false }
                ],
                throwOnError: false
            })
            window.katexRenderCache?.add(pageId)
        }
    } catch (error) {
        console.error('Failed to render math:', error)
    }
}

// Export function to trigger KaTeX rendering for a page (used by parent components)
export const triggerPageMathRender = async (pageId: string): Promise<void> => {
    // Find all elements matching the page
    const pageElements = document.querySelectorAll(`[data-page-id="${pageId}"]`)
    for (const element of Array.from(pageElements)) {
        if (element instanceof HTMLElement) {
            await renderKatexInElement(element, pageId, true)
        }
    }
}

interface StorybookPageRendererProps {
    page: StorybookPageData
    width: number
    height: number
    className?: string
}

// Extract dimensions from HTML viewport meta or body style
function getHtmlDimensions(html: string): { width: number; height: number } {
    const viewportMatch = html.match(/width=(\d+),\s*height=(\d+)/)
    if (viewportMatch) {
        return {
            width: parseInt(viewportMatch[1], 10),
            height: parseInt(viewportMatch[2], 10)
        }
    }
    const styleMatch = html.match(/width:\s*(\d+)px;\s*height:\s*(\d+)px/)
    if (styleMatch) {
        return {
            width: parseInt(styleMatch[1], 10),
            height: parseInt(styleMatch[2], 10)
        }
    }
    return { width: 1920, height: 1080 }
}

// Extract and scope styles from HTML for direct DOM rendering
function processHtmlForDirectRender(
    html: string,
    scopeId: string
): {
    styles: string
    bodyContent: string
    originalWidth: number
    originalHeight: number
} {
    const dimensions = getHtmlDimensions(html)

    // Extract style tags
    let styles = ''
    const styleRegex = /<style[^>]*>([\s\S]*?)<\/style>/gi
    let match
    while ((match = styleRegex.exec(html)) !== null) {
        styles += match[1] + '\n'
    }

    // Extract body content
    let bodyContent = html
    const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i)
    if (bodyMatch) {
        bodyContent = bodyMatch[1]
    } else {
        // If no body tag, remove head and html tags
        bodyContent = bodyContent.replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '')
        bodyContent = bodyContent.replace(/<\/?(?:html|body)[^>]*>/gi, '')
        bodyContent = bodyContent.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    }

    // Scope styles by wrapping in a unique class selector
    if (styles) {
        // Wrap all styles to be scoped under the unique container
        styles = `.${scopeId} { ${styles} }`
    }

    return {
        styles,
        bodyContent: bodyContent.trim(),
        originalWidth: dimensions.width,
        originalHeight: dimensions.height
    }
}

function isImageOnlyHtml(html: string): boolean {
    const normalized = html.toLowerCase()
    if (
        normalized.includes('page-type" content="text-only"') ||
        normalized.includes('data-type="text-only"') ||
        normalized.includes('page-type" content="combined"') ||
        normalized.includes('data-type="combined"')
    ) {
        return false
    }
    if (normalized.includes('class="text-section"')) {
        return false
    }
    return true
}

// Main page renderer component with forwardRef for react-pageflip compatibility
export const StorybookPageRenderer = forwardRef<
    HTMLDivElement,
    StorybookPageRendererProps
>(({ page, width, height, className }, ref) => {
    const { t } = useTranslation()
    const contentRef = useRef<HTMLDivElement>(null)

    // Generate unique scope ID for this page
    const scopeId = useMemo(() => `storybook-page-${page.id}`, [page.id])

    // Process HTML content
    const processedHtml = useMemo(() => {
        if (!page.htmlContent) return null
        return processHtmlForDirectRender(page.htmlContent, scopeId)
    }, [page.htmlContent, scopeId])
    const shouldCover = useMemo(() => {
        if (!page.htmlContent) return false
        return isImageOnlyHtml(page.htmlContent)
    }, [page.htmlContent])

    // Calculate scale to fit content within container
    const { scale, originalWidth, originalHeight } = useMemo(() => {
        if (!processedHtml)
            return { scale: 1, originalWidth: width, originalHeight: height }
        const scaleX = width / processedHtml.originalWidth
        const scaleY = height / processedHtml.originalHeight
        return {
            scale: shouldCover
                ? Math.max(scaleX, scaleY)
                : Math.min(scaleX, scaleY),
            originalWidth: processedHtml.originalWidth,
            originalHeight: processedHtml.originalHeight
        }
    }, [processedHtml, width, height, shouldCover])

    // Render math with KaTeX after content is mounted and when page becomes visible
    useEffect(() => {
        if (!contentRef.current || !page.htmlContent) return

        // Use requestAnimationFrame to ensure DOM is ready
        const timeoutId = setTimeout(() => {
            if (contentRef.current) {
                renderKatexInElement(contentRef.current, page.id)
            }
        }, 100)

        return () => clearTimeout(timeoutId)
    }, [page.htmlContent, page.id])

    // Render HTML content using direct DOM injection
    if (processedHtml) {
        const scaledWidth = originalWidth * scale
        const scaledHeight = originalHeight * scale
        const offsetX = (width - scaledWidth) / 2
        const offsetY = (height - scaledHeight) / 2

        return (
            <div
                ref={ref}
                className={cn(
                    'relative overflow-hidden bg-grey-3 dark:bg-[#0d1411]',
                    className
                )}
                style={{ width, height }}
            >
                {/* Scoped styles */}
                {processedHtml.styles && (
                    <style
                        dangerouslySetInnerHTML={{
                            __html: processedHtml.styles
                        }}
                    />
                )}

                {/* Content container with scaling */}
                <div
                    ref={contentRef}
                    data-page-id={page.id}
                    className={`${scopeId} absolute`}
                    style={{
                        width: originalWidth,
                        height: originalHeight,
                        transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
                        transformOrigin: 'top left',
                        fontSize: 'initial',
                        lineHeight: 'initial',
                        color: 'initial'
                    }}
                    dangerouslySetInnerHTML={{
                        __html: processedHtml.bodyContent
                    }}
                />
            </div>
        )
    }

    // Fallback: render image URL directly if no HTML content
    return (
        <div
            ref={ref}
            className={cn(
                'relative overflow-hidden bg-grey-3 dark:bg-[#0d1411]',
                className
            )}
            style={{ width, height }}
        >
            {page.imageUrl ? (
                <img
                    src={page.imageUrl}
                    alt={`Page ${page.pageNumber}`}
                    className="h-full w-full object-cover"
                />
            ) : (
                <div className="h-full w-full flex items-center justify-center text-black/60 dark:text-white/50">
                    {t('storybook.noImage')}
                </div>
            )}
        </div>
    )
})

// Add display name for debugging
StorybookPageRenderer.displayName = 'StorybookPageRenderer'

// Simple component for thumbnail display
interface StorybookPageThumbnailProps {
    page: StorybookPageData
    isActive: boolean
    onClick: () => void
    className?: string
    overrideImageUrl?: string | null
}

// Thumbnail dimensions
const THUMB_WIDTH = 64
const THUMB_HEIGHT = 80

export function StorybookPageThumbnail({
    page,
    isActive,
    onClick,
    className,
    overrideImageUrl
}: StorybookPageThumbnailProps): ReactElement {
    const { t } = useTranslation()
    const thumbRef = useRef<HTMLDivElement>(null)
    const imageOverride =
        typeof overrideImageUrl === 'string' && overrideImageUrl.length > 0
            ? overrideImageUrl
            : null

    // Generate unique scope ID for thumbnail
    const thumbScopeId = useMemo(() => `storybook-thumb-${page.id}`, [page.id])

    // Process HTML for thumbnail
    const processedThumbHtml = useMemo(() => {
        if (!page.htmlContent) return null
        return processHtmlForDirectRender(page.htmlContent, thumbScopeId)
    }, [page.htmlContent, thumbScopeId])

    // Calculate thumbnail scale
    const thumbStyle = useMemo(() => {
        if (!processedThumbHtml) return null
        const scale = Math.max(
            THUMB_WIDTH / processedThumbHtml.originalWidth,
            THUMB_HEIGHT / processedThumbHtml.originalHeight
        )
        const scaledWidth = processedThumbHtml.originalWidth * scale
        const scaledHeight = processedThumbHtml.originalHeight * scale
        const offsetX = (THUMB_WIDTH - scaledWidth) / 2
        const offsetY = (THUMB_HEIGHT - scaledHeight) / 2
        return {
            width: processedThumbHtml.originalWidth,
            height: processedThumbHtml.originalHeight,
            transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
            transformOrigin: 'top left'
        }
    }, [processedThumbHtml])

    // Render math in thumbnails
    useEffect(() => {
        if (!thumbRef.current || !page.htmlContent) return

        const renderMath = async () => {
            try {
                await loadKatexScripts()
                if (window.renderMathInElement && thumbRef.current) {
                    window.renderMathInElement(thumbRef.current, {
                        delimiters: [
                            { left: '$$', right: '$$', display: true },
                            { left: '$', right: '$', display: false },
                            { left: '\\[', right: '\\]', display: true },
                            { left: '\\(', right: '\\)', display: false }
                        ],
                        throwOnError: false
                    })
                }
            } catch (error) {
                console.error('Failed to render thumbnail math:', error)
            }
        }

        renderMath()
    }, [page.htmlContent, page.id])

    return (
        <button
            onClick={onClick}
            className={cn(
                'relative h-[4.5rem] w-[3.5rem] flex-shrink-0 overflow-hidden rounded-lg border transition-all duration-200 sm:h-20 sm:w-16',
                isActive
                    ? 'border-sky-blue dark:border-[#bfefff]'
                    : 'border-grey/60 opacity-60 hover:opacity-100 dark:border-white/5',
                className
            )}
        >
            {imageOverride ? (
                <img
                    src={imageOverride}
                    alt={t('storybook.viewer.pageAlt', {
                        page: page.pageNumber
                    })}
                    className="h-full w-full object-cover"
                />
            ) : processedThumbHtml && thumbStyle ? (
                <div className="relative w-full h-full overflow-hidden bg-grey-3 dark:bg-[#0d1411]">
                    {/* Scoped styles for thumbnail */}
                    {processedThumbHtml.styles && (
                        <style
                            dangerouslySetInnerHTML={{
                                __html: processedThumbHtml.styles
                            }}
                        />
                    )}
                    {/* Scaled content */}
                    <div
                        ref={thumbRef}
                        className={`${thumbScopeId} absolute pointer-events-none`}
                        style={{
                            ...thumbStyle,
                            fontSize: 'initial',
                            lineHeight: 'initial',
                            color: 'initial'
                        }}
                        dangerouslySetInnerHTML={{
                            __html: processedThumbHtml.bodyContent
                        }}
                    />
                </div>
            ) : page.imageUrl ? (
                <img
                    src={page.imageUrl}
                    alt={t('storybook.viewer.pageAlt', {
                        page: page.pageNumber
                    })}
                    className="h-full w-full object-cover"
                />
            ) : (
                <div className="h-full w-full bg-grey-3 flex items-center justify-center dark:bg-gray-800">
                    <span className="text-black/40 text-xs dark:text-white/30">
                        {page.pageNumber}
                    </span>
                </div>
            )}
            {/* Only show page number for image pages (using display page number) */}
            {page.displayPageNumber != null && (
                <span className="absolute bottom-1 right-1 rounded-full bg-black/60 px-2 text-[10px] font-semibold text-white">
                    {page.displayPageNumber}
                </span>
            )}
        </button>
    )
}
