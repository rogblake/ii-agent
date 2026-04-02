import { useRef, useState, useEffect, useCallback, useMemo } from 'react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { Icon } from '../ui/icon'
import {
    selectActiveSessionId,
    useAppSelector
} from '@/state'
import { PresentationListResponse } from '@/typings/agent'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { sessionService } from '@/services/session.service'
import { slideService } from '@/services/slide.service'
import { SlidesViewer } from '../slides-viewer'
import { useLocation } from 'react-router'
import {
    SlideDesignModeView,
    useOptionalDesignModeContext
} from '../design-mode'
import { NanoBananaDesignModeView } from '../design-mode/nano-banana'

interface SlideContent {
    slideNumber: number
    content: string
    isImageSlide?: boolean
    imageUrl?: string
}

// Helper function to detect if a slide is an image slide
const detectImageSlide = (
    content: string
): { isImageSlide: boolean; imageUrl?: string } => {
    // Check for data attribute in body tag
    const bodyMatch = content.match(/data-is-image-slide="true"/)
    const urlMatch = content.match(/data-image-url="([^"]+)"/)

    if (bodyMatch && urlMatch) {
        return { isImageSlide: true, imageUrl: urlMatch[1] }
    }

    // Check for meta tag
    const metaMatch = content.match(
        /<meta\s+name="slide-type"\s+content="image"/
    )
    if (metaMatch) {
        // Extract image URL from img src
        const imgSrcMatch = content.match(/<img[^>]+src="([^"]+)"/)
        if (imgSrcMatch) {
            return { isImageSlide: true, imageUrl: imgSrcMatch[1] }
        }
    }

    return { isImageSlide: false }
}

interface SlidesResultProps {
    className?: string
    hideHeader?: boolean
    onPresentationDataLoad?: (data: {
        name: string
        slideCount: number
    }) => void
    externalFullscreenTrigger?: boolean
    onFullscreenTriggered?: () => void
    slideViewerClassName?: string
    readOnly?: boolean
    onSlidesLoad?: (slides: SlideContent[]) => void
    activeSlideIndex?: number
    onActiveSlideChange?: (index: number) => void
    fullscreenStartIndex?: number
}

const SlidesResult = ({
    className,
    hideHeader = false,
    externalFullscreenTrigger,
    slideViewerClassName,
    activeSlideIndex,
    fullscreenStartIndex,
    onPresentationDataLoad,
    onFullscreenTriggered,
    onSlidesLoad,
    onActiveSlideChange
}: SlidesResultProps) => {
    const { t } = useTranslation()
    const location = useLocation()

    const fullscreenContainerRef = useRef<HTMLDivElement>(null)
    const fullscreenIframeRef = useRef<HTMLIFrameElement>(null)
    const [isFullscreenOpen, setIsFullscreenOpen] = useState(false)
    const [currentSlideIndex, setCurrentSlideIndex] = useState(0)
    const [isTransitioning, setIsTransitioning] = useState(false)
    const [slidesData, setSlidesData] =
        useState<PresentationListResponse | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [isDownloading, setIsDownloading] = useState(false)
    const [downloadProgress, setDownloadProgress] = useState({
        current: 0,
        total: 0,
        message: '',
        percent: 0
    })
    const { socket } = useSocketIOContext()

    const activeSessionId = useAppSelector(selectActiveSessionId)

    // Design mode integration
    const designModeContext = useOptionalDesignModeContext()
    const isDesignModeEnabled = designModeContext?.isEnabled ?? false

    const isShareMode = useMemo(
        () =>
            location.pathname.includes('/share/') ||
            location.pathname.includes('/presentations/'),
        [location.pathname]
    )

    const sanitizeLegacyEditableArtifacts = useCallback(
        (html: string): string => {
            if (!html) return html
            if (typeof DOMParser === 'undefined') return html

            try {
                const parser = new DOMParser()
                const doc = parser.parseFromString(html, 'text/html')

                const isEditableRendererStyle = (cssText: string) => {
                    const hay = (cssText || '').toLowerCase()
                    if (!hay.includes('.editable')) return false
                    return (
                        hay.includes('#ff6b75') ||
                        hay.includes('.editable-img') ||
                        hay.includes('.drop-zone') ||
                        hay.includes('.image-preview')
                    )
                }

                doc.querySelectorAll('style').forEach((styleTag) => {
                    const cssText = styleTag.textContent || ''
                    if (isEditableRendererStyle(cssText)) {
                        styleTag.remove()
                    }
                })

                doc.querySelectorAll<HTMLElement>(
                    '.editable, .editable-img, .editing'
                ).forEach((el) => {
                    el.classList.remove('editable', 'editable-img', 'editing')
                    if (!el.className.trim()) {
                        el.removeAttribute('class')
                    }
                })

                doc.querySelectorAll<HTMLElement>('[data-edit-id]').forEach(
                    (el) => el.removeAttribute('data-edit-id')
                )
                doc.querySelectorAll<HTMLElement>('[data-img-id]').forEach(
                    (el) => el.removeAttribute('data-img-id')
                )
                doc.querySelectorAll<HTMLElement>('[contenteditable]').forEach(
                    (el) => el.removeAttribute('contenteditable')
                )

                return doc.documentElement.outerHTML
            } catch {
                return html
            }
        },
        []
    )

    // Function to process slide content and change body width to 100%
    const processSlideContent = (htmlContent: string): string => {
        const sanitized = sanitizeLegacyEditableArtifacts(htmlContent)
        // Replace body width from fixed pixels to 100%
        return sanitized.replace(/body\s*{([^}]*)}/g, (_match, rules) => {
            const modifiedRules = rules.replace(
                /width:\s*\d+px;?/gi,
                'width: 100%;'
            )
            return `body {${modifiedRules}}`
        })
    }

    // Extract slide content from API response
    const slideContent = useMemo(
        () =>
            slidesData?.presentations?.[0]?.slides?.map((slide) => {
                const content = processSlideContent(slide.slide_content || '')
                const { isImageSlide, imageUrl } = detectImageSlide(content)
                return {
                    slideNumber: slide.slide_number || 1,
                    content,
                    isImageSlide,
                    imageUrl
                }
            }) || [],
        [slidesData]
    )

    // Get presentation name from API response
    const presentationName = useMemo(
        () =>
            slidesData?.presentations?.[0]?.name ||
            t('agent.slides.defaultName'),
        [slidesData, t]
    )

    // Notify parent when presentation data is loaded
    useEffect(() => {
        if (slidesData && onPresentationDataLoad) {
            onPresentationDataLoad({
                name: presentationName,
                slideCount: slideContent.length
            })
        }
        if (slideContent.length > 0 && onSlidesLoad) {
            onSlidesLoad(slideContent)
        }
    }, [
        slidesData,
        onSlidesLoad,
        presentationName,
        slideContent.length,
        onPresentationDataLoad
    ])

    // Handle external fullscreen trigger
    useEffect(() => {
        if (externalFullscreenTrigger && fullscreenContainerRef.current) {
            fullscreenContainerRef.current
                .requestFullscreen()
                .then(() => {
                    setIsFullscreenOpen(true)
                    setCurrentSlideIndex(fullscreenStartIndex ?? 0)
                    onFullscreenTriggered?.()
                })
                .catch((error) => {
                    console.error('Failed to enter fullscreen:', error)
                    toast.error(t('agent.slides.errors.enterFullscreen'))
                    onFullscreenTriggered?.()
                })
        }
    }, [
        externalFullscreenTrigger,
        onFullscreenTriggered,
        fullscreenStartIndex,
        t
    ])

    // Fetch slides data from API
    const fetchSlides = useCallback(async () => {
        if (!activeSessionId) return

        setIsLoading(true)
        try {
            const data = isShareMode
                ? await sessionService.getPublicSessionSlides(activeSessionId)
                : await sessionService.getSessionSlides(activeSessionId)
            setSlidesData(data)
        } catch (error) {
            console.error('Failed to fetch slides:', error)
            toast.error(t('agent.slides.errors.loadSlides'))
        } finally {
            setIsLoading(false)
        }
    }, [activeSessionId, isShareMode, t])

    const handleRefresh = () => {
        fetchSlides()
        if (socket?.connected) {
            socket.emit('chat_message', {
                type: 'sandbox_status',
                session_uuid: activeSessionId
            })
        }
    }

    const handlePresent = async () => {
        if (!fullscreenContainerRef.current) return

        try {
            await fullscreenContainerRef.current.requestFullscreen()
            setIsFullscreenOpen(true)
            setCurrentSlideIndex(0)
        } catch (error) {
            console.error('Failed to enter fullscreen:', error)
            toast.error(t('agent.slides.errors.enterFullscreen'))
        }
    }

    const handleDownload = async () => {
        if (!activeSessionId || isDownloading) return

        setIsDownloading(true)
        // Reset progress state
        setDownloadProgress({ current: 0, total: 0, message: '', percent: 0 })

        try {
            const progressGenerator =
                await slideService.downloadSlidesWithProgress(
                    activeSessionId,
                    presentationName,
                    isShareMode
                )

            for await (const progress of progressGenerator) {
                if (progress.type === 'progress') {
                    setDownloadProgress({
                        current: progress.current || 0,
                        total: progress.total || 0,
                        message: progress.message || '',
                        percent: progress.percent || 0
                    })
                } else if (progress.type === 'complete') {
                    if (progress.pdf_base64 && progress.filename) {
                        slideService.downloadPDFFile(
                            progress.pdf_base64,
                            progress.filename
                        )
                        toast.success(t('agent.slides.toasts.downloadSuccess'))
                    }
                    setIsDownloading(false)
                    return
                } else if (progress.type === 'error') {
                    toast.error(
                        progress.message ||
                        t('agent.slides.errors.downloadSlides')
                    )
                    setIsDownloading(false)
                    return
                }
            }
        } catch (error) {
            console.error('Failed to download:', error)
            toast.error(t('agent.slides.errors.downloadSlides'))
            setIsDownloading(false)
        }
    }

    const handleNextSlide = useCallback(() => {
        if (isTransitioning) return
        const nextIndex = Math.min(
            currentSlideIndex + 1,
            slideContent.length - 1
        )
        if (nextIndex === currentSlideIndex) return

        setIsTransitioning(true)
        setCurrentSlideIndex(nextIndex)

        setTimeout(() => {
            setIsTransitioning(false)
        }, 300)
    }, [slideContent.length, currentSlideIndex, isTransitioning])

    const handlePrevSlide = useCallback(() => {
        if (isTransitioning) return
        const prevIndex = Math.max(currentSlideIndex - 1, 0)
        if (prevIndex === currentSlideIndex) return

        setIsTransitioning(true)
        setCurrentSlideIndex(prevIndex)

        setTimeout(() => {
            setIsTransitioning(false)
        }, 300)
    }, [currentSlideIndex, isTransitioning])

    const handleKeyDown = useCallback(
        (event: KeyboardEvent) => {
            if (!isFullscreenOpen) return

            switch (event.key) {
                case 'ArrowRight':
                case ' ':
                    event.preventDefault()
                    handleNextSlide()
                    break
                case 'ArrowLeft':
                    event.preventDefault()
                    handlePrevSlide()
                    break
                case 'Escape':
                    event.preventDefault()
                    document.exitFullscreen()
                    break
            }
        },
        [isFullscreenOpen, handleNextSlide, handlePrevSlide]
    )

    const handleFullscreenChange = useCallback(() => {
        if (!document.fullscreenElement) {
            setIsFullscreenOpen(false)
        }
    }, [])

    const scaleIframeToFitViewport = (
        iframe: HTMLIFrameElement | null,
        opts: {
            designWidth?: number
            designHeight?: number
            allowUpscale?: boolean
            padding?: number
        } = {}
    ) => {
        if (!iframe || !iframe.contentDocument) return 1

        const {
            designWidth = 1280,
            designHeight = 720,
            allowUpscale = true,
            padding = 0
        } = opts

        const doc = iframe.contentDocument

        // Measure iframe content height (natural height)
        const contentHeight =
            Math.max(
                doc.body.scrollHeight,
                doc.body.offsetHeight,
                doc.documentElement.offsetHeight
            ) || designHeight
        const contentWidth =
            Math.max(
                doc.body.scrollWidth,
                doc.body.offsetWidth,
                doc.documentElement.offsetWidth
            ) || designWidth

        const viewportWidth = Math.max(0, window.innerWidth - padding * 2)
        const viewportHeight = Math.max(0, window.innerHeight - padding * 2)

        const heightScale = viewportHeight / contentHeight
        const widthScale = viewportWidth / contentWidth

        // Fit within both dimensions to avoid horizontal overflow showing neighboring slides
        let scale = Math.min(heightScale, widthScale)
        if (!allowUpscale) scale = Math.min(scale, 1)

        // Apply scaling to the iframe itself
        iframe.style.transformOrigin = 'center center'
        iframe.style.transform = `scale(${scale})`

        // Force iframe base dimensions (before scaling)
        iframe.style.width = `${contentWidth}px`
        iframe.style.height = `${contentHeight}px`

        // Center horizontally
        iframe.style.margin = '0 auto'
        iframe.style.display = 'block'

        return scale
    }

    useEffect(() => {
        fetchSlides()
    }, [fetchSlides])

    // Track previous design mode state to detect transitions
    const prevDesignModeEnabledRef = useRef(isDesignModeEnabled)
    useEffect(() => {
        // When transitioning from design mode (enabled) to build mode (disabled),
        // refetch slides to get the updated content from the database
        if (prevDesignModeEnabledRef.current && !isDesignModeEnabled) {
            fetchSlides()
        }
        prevDesignModeEnabledRef.current = isDesignModeEnabled
    }, [isDesignModeEnabled, fetchSlides])

    useEffect(() => {
        window.addEventListener('keydown', handleKeyDown)
        document.addEventListener('fullscreenchange', handleFullscreenChange)
        return () => {
            window.removeEventListener('keydown', handleKeyDown)
            document.removeEventListener(
                'fullscreenchange',
                handleFullscreenChange
            )
        }
    }, [handleKeyDown, handleFullscreenChange])

    // Calculate scale for fullscreen slides to fit full height
    useEffect(() => {
        const iframe = fullscreenIframeRef.current
        if (!iframe || !isFullscreenOpen) return

        const applyScale = () =>
            setTimeout(
                () =>
                    scaleIframeToFitViewport(iframe, {
                        designWidth: 1280,
                        designHeight: 720
                    }),
                200
            )

        iframe.addEventListener('load', applyScale)
        applyScale()
        window.addEventListener('resize', applyScale)

        return () => {
            iframe.removeEventListener('load', applyScale)
            window.removeEventListener('resize', applyScale)
        }
    }, [isFullscreenOpen, currentSlideIndex])

    if (isLoading) {
        return (
            <div
                className={`flex-1 w-full h-full bg-white dark:bg-charcoal flex items-center justify-center ${className}`}
            >
                <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-2"></div>
                    <p>{t('common.loading')}</p>
                </div>
            </div>
        )
    }

    if (slideContent.length === 0) return null

    // Design mode view - show full deck with design mode capabilities
    if (isDesignModeEnabled && activeSessionId && presentationName) {
        // Check if all slides are image slides (nano banana)
        const allImageSlides =
            slideContent.length > 0 &&
            slideContent.every((s) => s.isImageSlide)

        if (allImageSlides) {
            // Use nano banana design mode for image-based slides
            return (
                <NanoBananaDesignModeView
                    sessionId={activeSessionId}
                    presentationName={presentationName}
                    slides={slideContent
                        .filter((s) => s.imageUrl)
                        .map((s) => ({
                            slideNumber: s.slideNumber,
                            imageUrl: s.imageUrl!
                        }))}
                    className={className}
                />
            )
        }

        // Use regular design mode for HTML/CSS slides
        return (
            <SlideDesignModeView
                sessionId={activeSessionId}
                presentationName={presentationName}
                slideCount={slideContent.length}
                className={className}
            />
        )
    }

    return (
        <div
            className={`flex-1 w-full h-full bg-white dark:bg-charcoal ${className}`}
        >
            {!hideHeader && (
                <div className="w-full flex items-center justify-between pl-6 pr-4 py-2 gap-4 overflow-hidden border-b border-white/30">
                    <div className="rounded-lg w-full flex items-center gap-4 group transition-colors">
                        <button
                            className="cursor-pointer"
                            onClick={handleRefresh}
                        >
                            <Icon
                                name="refresh"
                                className="size-5 stroke-black dark:stroke-white"
                            />
                        </button>
                        <span className="text-sm text-black bg-[#f4f4f4] dark:bg-white line-clamp-1 break-all flex-1 font-semibold px-4 py-1 rounded-sm">
                            {presentationName}
                        </span>
                    </div>
                    <div className="flex items-center gap-4">
                        <button
                            className="cursor-pointer group disabled:opacity-50 disabled:cursor-not-allowed"
                            onClick={handleDownload}
                            title={t('agent.slides.actions.downloadAsPdf')}
                            disabled={isDownloading}
                        >
                            {isDownloading ? (
                                <div className="size-5 animate-spin rounded-full border-2 border-gray-300 dark:border-gray-600 border-t-black dark:border-t-white" />
                            ) : (
                                <svg
                                    className="size-5 stroke-black dark:stroke-white group-hover:opacity-80 transition-opacity"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    strokeWidth="2"
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"
                                    />
                                </svg>
                            )}
                        </button>
                        <button
                            className="cursor-pointer hidden md:inline"
                            onClick={handlePresent}
                            title={t('agent.slides.actions.presentFullscreen')}
                        >
                            <Icon
                                name="fullscreen"
                                className="size-5 fill-black dark:fill-white"
                            />
                        </button>
                    </div>
                </div>
            )}
            <SlidesViewer
                slides={slideContent}
                className={`h-hull max-h-[calc(100vh-159px)] overflow-auto ${slideViewerClassName}`}
                disableEditing={true}
                onSlideContentChange={undefined}
                activeSlideIndex={activeSlideIndex}
                onActiveSlideChange={onActiveSlideChange}
            />
            {/* Fullscreen container */}
            <div
                ref={fullscreenContainerRef}
                className={`${isFullscreenOpen
                        ? 'fixed inset-0 z-[9999] bg-black'
                        : 'hidden'
                    }`}
            >
                <div className="relative w-full h-full flex items-center justify-center">
                    <div className="absolute top-4 right-4 z-10 bg-black/50 text-white px-3 py-1 rounded text-sm">
                        {currentSlideIndex + 1} / {slideContent.length}
                    </div>

                    <div className="flex items-center gap-4 absolute z-10 bottom-4 right-4">
                        <button
                            onClick={handlePrevSlide}
                            disabled={currentSlideIndex === 0}
                            className="z-10 p-2 text-white bg-black cursor-pointer opacity-30 hover:opacity-100 rounded-full disabled:cursor-not-allowed"
                        >
                            <Icon
                                name="arrow-left-2"
                                className="size-6 fill-white"
                            />
                        </button>

                        <button
                            onClick={handleNextSlide}
                            disabled={
                                currentSlideIndex === slideContent.length - 1
                            }
                            className="z-10 p-2 text-white bg-black cursor-pointer opacity-30 hover:opacity-100 rounded-full disabled:cursor-not-allowed"
                        >
                            <Icon
                                name="arrow-left-2"
                                className="size-6 fill-white rotate-180"
                            />
                        </button>
                    </div>

                    {/* Close button */}
                    <button
                        onClick={() => document.exitFullscreen()}
                        className="absolute top-4 left-4 z-10 p-2 text-white hover:bg-white/20 rounded-full"
                    >
                        <Icon name="x" className="size-6 fill-white" />
                    </button>

                    {/* Slide container with animations */}
                    <div className="w-full h-full relative overflow-hidden">
                        <div
                            className="w-full h-full flex transition-transform duration-300 ease-in-out"
                            style={{
                                transform: `translateX(-${currentSlideIndex * 100}%)`
                            }}
                        >
                            {slideContent.map((slide, index) => (
                                <div
                                    key={`slide-${slide.slideNumber}`}
                                    className="w-full h-full flex-shrink-0 flex items-center justify-center overflow-hidden"
                                >
                                    {slide.isImageSlide && slide.imageUrl ? (
                                        <img
                                            src={slide.imageUrl}
                                            alt={t('agent.slides.slideAlt', {
                                                number: slide.slideNumber
                                            })}
                                            className="max-w-full max-h-full object-contain"
                                        />
                                    ) : (
                                        <iframe
                                            ref={
                                                index === currentSlideIndex
                                                    ? fullscreenIframeRef
                                                    : undefined
                                            }
                                            srcDoc={slide.content}
                                            className="border-0"
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Loading overlay for download */}
            {isDownloading && (
                <div className="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-charcoal border border-sky-blue rounded-xl p-6 flex flex-col items-center gap-4 w-80 max-w-sm shadow-xl">
                        <div className="animate-spin rounded-full h-12 w-12 border-4 border-sky-blue border-t-black dark:border-t-black" />
                        <p className="text-black dark:text-white font-medium">
                            {t('agent.slides.downloadOverlay.generatingPdf')}
                        </p>

                        <div className="w-full space-y-3">
                            <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
                                <span>
                                    {downloadProgress.total > 0 &&
                                        downloadProgress.current > 0
                                        ? t(
                                            'agent.slides.downloadOverlay.slideOfTotal',
                                            {
                                                current:
                                                    downloadProgress.current,
                                                total: downloadProgress.total
                                            }
                                        )
                                        : t(
                                            'agent.slides.downloadOverlay.starting'
                                        )}
                                </span>
                                <span>{downloadProgress.percent}%</span>
                            </div>
                            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                <div
                                    className="bg-sky-blue h-2 rounded-full transition-all duration-300"
                                    style={{
                                        width: `${downloadProgress.percent}%`
                                    }}
                                />
                            </div>
                            {downloadProgress.message && (
                                <p className="text-xs text-gray-500 dark:text-gray-400 text-center leading-relaxed break-words">
                                    {downloadProgress.message}
                                </p>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

export default SlidesResult
