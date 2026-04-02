import { useState, useRef, useEffect, useMemo } from 'react'
import {
    EditableHtmlRenderer,
    type EditableHtmlRendererRef
} from './editable-html'

interface Slide {
    slideNumber: number
    content: string
    description?: string
    isImageSlide?: boolean
    imageUrl?: string
}

interface SlidesViewerProps {
    slides?: Slide[]
    className?: string
    disableEditing?: boolean
    onSlideContentChange?: (
        slideNumber: number,
        content: string,
        title?: string
    ) => void
    activeSlideIndex?: number
    onActiveSlideChange?: (index: number) => void
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
    const metaMatch = content.match(/<meta\s+name="slide-type"\s+content="image"/)
    if (metaMatch) {
        // Extract image URL from img src
        const imgSrcMatch = content.match(/<img[^>]+src="([^"]+)"/)
        if (imgSrcMatch) {
            return { isImageSlide: true, imageUrl: imgSrcMatch[1] }
        }
    }

    return { isImageSlide: false }
}

export function SlidesViewer({
    slides = [],
    className,
    disableEditing = false,
    onSlideContentChange,
    activeSlideIndex,
    onActiveSlideChange
}: SlidesViewerProps) {
    const viewerRef = useRef<HTMLDivElement>(null)
    const slideRefs = useRef<(HTMLDivElement | null)[]>([])

    // Scroll to active slide when activeSlideIndex changes
    useEffect(() => {
        if (
            activeSlideIndex !== undefined &&
            activeSlideIndex >= 0 &&
            slideRefs.current[activeSlideIndex]
        ) {
            slideRefs.current[activeSlideIndex]?.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            })
        }
    }, [activeSlideIndex])

    // Observe which slide is in view and update activeSlideIndex
    useEffect(() => {
        if (!onActiveSlideChange || !viewerRef.current) return

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        const slideIndex = slideRefs.current.findIndex(
                            (ref) => ref === entry.target
                        )
                        if (slideIndex !== -1) {
                            onActiveSlideChange(slideIndex)
                        }
                    }
                })
            },
            {
                root: viewerRef.current,
                threshold: 0.5
            }
        )

        slideRefs.current.forEach((ref) => {
            if (ref) observer.observe(ref)
        })

        return () => observer.disconnect()
    }, [onActiveSlideChange, slides.length])
    const [scales, setScales] = useState<number[]>(
        new Array(slides.length).fill(1)
    )
    const [slideHeights, setSlideHeights] = useState<number[]>(
        new Array(slides.length).fill(720)
    )
    const scalesRef = useRef<number[]>([])
    const slideHeightsRef = useRef<number[]>([])
    const resizeObserverRef = useRef<ResizeObserver | null>(null)
    const rafIdRef = useRef<number | null>(null)
    const containerRefs = useRef<(HTMLDivElement | null)[]>([])
    const slideContentRefs = useRef<(HTMLDivElement | null)[]>([])
    const editableRefs = useRef<(EditableHtmlRendererRef | null)[]>([])

    // Function to scope CSS for each slide
    const scopeSlideStyles = (htmlContent: string, slideId: string): string => {
        const parser = new DOMParser()
        const doc = parser.parseFromString(htmlContent, 'text/html')

        // Find all style tags
        const styleTags = doc.querySelectorAll('style')

        styleTags.forEach((styleTag) => {
            let cssText = styleTag.textContent || ''

            // First, modify body width to 100% if it has a fixed width
            cssText = cssText.replace(/body\s*{([^}]*)}/g, (_match, rules) => {
                // Replace any width declaration with 100%
                const modifiedRules = rules.replace(
                    /width:\s*\d+px;?/gi,
                    'width: 100%;'
                )
                return `body {${modifiedRules}}`
            })

            // Add scope to each CSS rule
            // This regex matches CSS selectors (everything before {)
            cssText = cssText.replace(/([^{}]+){/g, (match, selector) => {
                // Skip keyframes and media queries
                if (
                    selector.includes('@keyframes') ||
                    selector.includes('@media')
                ) {
                    return match
                }

                // Process each selector in a comma-separated list
                const scopedSelectors = selector
                    .split(',')
                    .map((sel: string) => {
                        sel = sel.trim()

                        // Skip html and body selectors, replace with slide container
                        if (sel === 'html' || sel === 'body') {
                            return `[data-slide-id="${slideId}"]`
                        }

                        // Keep :root selector global for CSS custom properties
                        if (sel === ':root') {
                            return ':root'
                        }

                        // Keep @-rules global (like @font-face, @import, @charset)
                        if (sel.startsWith('@') && !sel.includes('{')) {
                            return sel
                        }

                        // Skip * selector - make it scoped
                        if (sel === '*') {
                            return `[data-slide-id="${slideId}"] *`
                        }

                        // Add scope to other selectors
                        const result = `[data-slide-id="${slideId}"] ${sel}`
                        return result
                    })
                    .join(', ')

                return scopedSelectors + ' {'
            })

            styleTag.textContent = cssText
        })

        // Also add to body for fallback
        if (doc.body) {
            doc.body.setAttribute('data-slide-id', slideId)
        }

        return doc.documentElement.outerHTML
    }

    // Process slides with scoped styles and detect image slides
    const processedSlides = useMemo(() => {
        return slides.map((slide) => {
            const { isImageSlide, imageUrl } = detectImageSlide(slide.content)
            return {
                content: scopeSlideStyles(slide.content, `${slide.slideNumber}`),
                isImageSlide: slide.isImageSlide || isImageSlide,
                imageUrl: slide.imageUrl || imageUrl
            }
        })
    }, [slides])

    useEffect(() => {
        scalesRef.current = scales
        slideHeightsRef.current = slideHeights
    }, [scales, slideHeights])

    useEffect(() => {
        const calculateScalesAndHeights = () => {
            const newScales: number[] = []
            const newHeights: number[] = []
            const previousScales = scalesRef.current
            const previousHeights = slideHeightsRef.current

            containerRefs.current.forEach((container, index) => {
                if (!container) {
                    newScales.push(previousScales[index] ?? 1)
                    newHeights.push(previousHeights[index] ?? 720)
                    return
                }

                const containerWidth = container.clientWidth
                if (containerWidth <= 0) {
                    newScales.push(previousScales[index] ?? 1)
                    newHeights.push(previousHeights[index] ?? 720)
                    return
                }

                const slideWidth = 1280
                const scale = containerWidth / slideWidth
                newScales.push(scale)

                // Get the actual height from the EditableHtmlRenderer
                const editableRef = editableRefs.current[index]
                if (editableRef) {
                    const actualHeight = editableRef.getContainerHeight()
                    // Calculate the scaled height
                    newHeights.push(actualHeight * scale)
                } else {
                    newHeights.push(720 * scale)
                }
            })

            setScales(newScales)
            setSlideHeights(newHeights)
        }

        const scheduleRecalc = () => {
            if (rafIdRef.current !== null) {
                cancelAnimationFrame(rafIdRef.current)
            }
            rafIdRef.current = requestAnimationFrame(calculateScalesAndHeights)
        }

        scheduleRecalc()
        window.addEventListener('resize', scheduleRecalc)

        if (viewerRef.current && typeof ResizeObserver !== 'undefined') {
            resizeObserverRef.current?.disconnect()
            resizeObserverRef.current = new ResizeObserver(scheduleRecalc)
            resizeObserverRef.current.observe(viewerRef.current)
        }

        return () => {
            window.removeEventListener('resize', scheduleRecalc)
            resizeObserverRef.current?.disconnect()
            resizeObserverRef.current = null
            if (rafIdRef.current !== null) {
                cancelAnimationFrame(rafIdRef.current)
                rafIdRef.current = null
            }
        }
    }, [processedSlides])

    const handleSlideContentChange = async (
        slideIndex: number,
        fullHtmlContent: string,
        changes: Record<string, string>
    ) => {
        const slide = slides[slideIndex]
        if (slide && changes && onSlideContentChange) {
            onSlideContentChange(
                slide.slideNumber,
                fullHtmlContent,
                changes.title
            )
        }
    }

    return (
        <div
            ref={viewerRef}
            className={`slides-viewer p-5 max-w-[1280px] m-auto ${className}`}
        >
            <div className="slides-container flex flex-col gap-8 items-center">
                {slides?.map((slide, index) => (
                    <div
                        key={slide.slideNumber}
                        ref={(el) => {
                            slideRefs.current[index] = el
                        }}
                        className="w-full max-w-[1080px]"
                    >
                        {slide.description && (
                            <p className="mb-4 whitespace-pre-line">
                                {slide.description}
                            </p>
                        )}
                        <div className="w-full max-w-[1080px] border border-white rounded-xl bg-white overflow-hidden">
                            <div
                                ref={(el) => {
                                    containerRefs.current[index] = el
                                }}
                                className="w-full overflow-hidden relative"
                                style={{
                                    height: `${slideHeights[index] ?? 720}px`
                                }}
                            >
                                <div
                                    ref={(el) => {
                                        slideContentRefs.current[index] = el
                                    }}
                                    className="w-[1280px] absolute top-0 left-0"
                                    style={{
                                        transform: `scale(${scales[index] ?? 1})`,
                                        transformOrigin: 'top left'
                                    }}
                                >
                                    {processedSlides[index]?.isImageSlide &&
                                        processedSlides[index]?.imageUrl ? (
                                        <div className="w-[1280px] h-[720px] bg-black flex items-center justify-center">
                                            <img
                                                src={
                                                    processedSlides[index]
                                                        .imageUrl!
                                                }
                                                alt={`Slide ${slide.slideNumber}`}
                                                className="max-w-full max-h-full object-contain"
                                            />
                                        </div>
                                    ) : (
                                        <EditableHtmlRenderer
                                            ref={(el) => {
                                                editableRefs.current[index] = el
                                            }}
                                            disableEditing={disableEditing}
                                            htmlContent={
                                                processedSlides[index]?.content
                                            }
                                            onContentChange={(
                                                fullHtmlContent,
                                                changes
                                            ) =>
                                                handleSlideContentChange(
                                                    index,
                                                    fullHtmlContent,
                                                    changes
                                                )
                                            }
                                        />
                                    )}
                                </div>
                                <div className="absolute right-4 bottom-4 text-xs h-7 px-4 flex justify-center items-center bg-black text-white rounded-4xl">
                                    <p>{`${index + 1} / ${slides?.length}`}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
