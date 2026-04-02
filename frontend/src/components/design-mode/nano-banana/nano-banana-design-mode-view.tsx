/**
 * Nano Banana Design Mode View
 *
 * Main component for editing AI-generated image slides in design mode.
 * Uses vision-based component detection to create interactive overlays
 * on top of slide images, enabling familiar click-to-edit UX.
 *
 * Key behaviors:
 * - Instructions are per-slide and independent (editing slide 4 doesn't affect slide 5)
 * - "Apply Changes" regenerates ALL slides with pending instructions in parallel
 * - Detection runs per-slide in parallel (no waiting for slide 1 before slide 2)
 * - Unmounting (toggle off design mode) cancels all in-flight requests (kill switch)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import axiosInstance from '@/lib/axios'
import { NanoBananaToolbar } from './nano-banana-toolbar'
import { NanoBananaSlidePanel } from './nano-banana-slide-panel'
import { NanoBananaInspector } from './nano-banana-inspector'
import { useNanoBananaDetection } from './use-nano-banana-detection'
import { useNanoBananaSelection } from './use-nano-banana-selection'
import { useNanoBananaInstructions } from './use-nano-banana-instructions'
import { useNanoBananaVersions } from './use-nano-banana-versions'
import type { NanoBananaSlideInfo } from './types'

interface NanoBananaDesignModeViewProps {
    sessionId: string
    presentationName: string
    slides: NanoBananaSlideInfo[]
    className?: string
    onSlideUpdated?: (slideNumber: number, newImageUrl: string) => void
}

export function NanoBananaDesignModeView({
    sessionId,
    presentationName,
    slides: initialSlides,
    className,
    onSlideUpdated
}: NanoBananaDesignModeViewProps) {
    const { t } = useTranslation()

    // Local slides state - starts from prop, updated internally after regeneration
    const [localSlides, setLocalSlides] =
        useState<NanoBananaSlideInfo[]>(initialSlides)

    // Sync with prop when it changes externally
    useEffect(() => {
        setLocalSlides(initialSlides)
    }, [initialSlides])

    // Update a single slide's image URL locally
    const updateSlideImage = useCallback(
        (slideNumber: number, newImageUrl: string) => {
            setLocalSlides((prev) =>
                prev.map((s) =>
                    s.slideNumber === slideNumber
                        ? { ...s, imageUrl: newImageUrl }
                        : s
                )
            )
            onSlideUpdated?.(slideNumber, newImageUrl)
        },
        [onSlideUpdated]
    )

    // Current active slide
    const [activeSlideIndex, setActiveSlideIndex] = useState(0)
    const activeSlide = localSlides[activeSlideIndex] || localSlides[0]

    // Per-slide regeneration tracking
    const [regeneratingSlides, setRegeneratingSlides] = useState<Set<number>>(
        new Set()
    )
    const [isRemovingBackground, setIsRemovingBackground] = useState(false)

    // AbortController for regeneration requests (kill switch)
    const regenAbortRef = useRef<AbortController | null>(null)
    const bgRemovalAbortRef = useRef<AbortController | null>(null)

    // Detection state (parallel per-slide, with AbortController)
    const {
        slideStates,
        detectSlide,
        retrySlide,
        redetectSlide,
        cancelAll: cancelAllDetections
    } = useNanoBananaDetection({
        sessionId,
        presentationName
    })

    // Selection state
    const {
        selectionMode,
        setSelectionMode,
        currentSelection,
        setSelection,
        clearSelection
    } = useNanoBananaSelection()

    // Instructions state (per-slide Map, local-only — no DB persistence)
    const {
        getInstructions,
        addInstruction,
        removeInstruction,
        clearSlideInstructions,
        clearAllInstructions,
        slidesWithInstructions,
        totalInstructionCount,
        hasAnyInstructions
    } = useNanoBananaInstructions()

    // Version state (for active slide)
    const {
        versions,
        currentVersionId,
        loadVersions,
        revertToVersion,
        isReverting
    } = useNanoBananaVersions({
        sessionId,
        presentationName,
        slideNumber: activeSlide?.slideNumber || 1
    })

    // Kill switch: cancel everything on unmount (design mode toggle-off)
    useEffect(() => {
        return () => {
            cancelAllDetections()
            regenAbortRef.current?.abort()
            bgRemovalAbortRef.current?.abort()
            clearAllInstructions()
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    // Handle slide click
    const handleSlideClick = useCallback(
        (slideIndex: number, slide: NanoBananaSlideInfo) => {
            setActiveSlideIndex(slideIndex)

            if (
                selectionMode === 'component' &&
                !slideStates.has(slide.slideNumber)
            ) {
                detectSlide(slide.slideNumber, slide.imageUrl)
            }
        },
        [selectionMode, slideStates, detectSlide]
    )

    // Clear selection when slide changes
    useEffect(() => {
        clearSelection()
    }, [activeSlideIndex, clearSelection])

    // Trigger detection when switching to component mode for the active slide
    useEffect(() => {
        if (
            selectionMode === 'component' &&
            activeSlide &&
            !slideStates.has(activeSlide.slideNumber)
        ) {
            detectSlide(activeSlide.slideNumber, activeSlide.imageUrl)
        }
    }, [selectionMode, activeSlide, slideStates, detectSlide])

    // Handle apply changes — regenerate ALL slides with pending instructions in parallel
    const handleApplyChanges = useCallback(async () => {
        if (!hasAnyInstructions) return

        // Build list of slides to regenerate
        const slidesToRegen = slidesWithInstructions
            .map((slideNum) => {
                const slide = localSlides.find(
                    (s) => s.slideNumber === slideNum
                )
                if (!slide) return null
                return {
                    slideNumber: slideNum,
                    slide,
                    instructions: getInstructions(slideNum)
                }
            })
            .filter(
                (
                    item
                ): item is {
                    slideNumber: number
                    slide: NanoBananaSlideInfo
                    instructions: ReturnType<typeof getInstructions>
                } => item !== null && item.instructions.length > 0
            )

        if (slidesToRegen.length === 0) return

        // Create a shared AbortController for all regen requests
        const controller = new AbortController()
        regenAbortRef.current = controller

        // Mark all as regenerating
        setRegeneratingSlides(
            new Set(slidesToRegen.map((s) => s.slideNumber))
        )

        // Regenerate all slides in parallel
        const results = await Promise.allSettled(
            slidesToRegen.map(async ({ slideNumber, slide, instructions }) => {
                const detectionState = slideStates.get(slideNumber)
                const components = detectionState?.components || []

                const response = await axiosInstance.post(
                    '/design-mode/nano-banana/regenerate',
                    {
                        session_id: sessionId,
                        presentation_name: presentationName,
                        slide_number: slideNumber,
                        current_image_url: slide.imageUrl,
                        instructions,
                        detected_components: components
                    },
                    { signal: controller.signal }
                )

                return { slideNumber, response }
            })
        )

        // Process results
        let successCount = 0
        let failCount = 0

        for (const result of results) {
            if (result.status === 'fulfilled') {
                const { slideNumber, response } = result.value
                if (response.data?.success) {
                    clearSlideInstructions(slideNumber)
                    const newImageUrl = response.data.new_image_url
                    if (newImageUrl) {
                        updateSlideImage(slideNumber, newImageUrl)
                        redetectSlide(slideNumber, newImageUrl)
                    }
                    successCount++
                } else {
                    failCount++
                }
            } else {
                // Ignore abort errors
                const reason = result.reason
                if (
                    reason?.name === 'CanceledError' ||
                    reason?.name === 'AbortError'
                )
                    continue
                failCount++
            }
        }

        setRegeneratingSlides(new Set())
        clearSelection()
        regenAbortRef.current = null

        // Reload versions for active slide
        await loadVersions()

        if (successCount > 0) {
            toast.success(
                successCount === 1
                    ? t(
                        'designMode.slideRegenerated',
                        'Slide regenerated successfully'
                    )
                    : t(
                        'designMode.slidesRegenerated',
                        `${successCount} slides regenerated successfully`
                    )
            )
        }
        if (failCount > 0) {
            toast.error(
                t(
                    'designMode.regenerationFailed',
                    `${failCount} slide(s) failed to regenerate`
                )
            )
        }
    }, [
        hasAnyInstructions,
        slidesWithInstructions,
        localSlides,
        getInstructions,
        slideStates,
        sessionId,
        presentationName,
        clearSlideInstructions,
        updateSlideImage,
        redetectSlide,
        clearSelection,
        loadVersions,
        t
    ])

    // Handle remove background (for active slide only)
    const handleRemoveBackground = useCallback(async () => {
        if (!activeSlide) return

        const controller = new AbortController()
        bgRemovalAbortRef.current = controller
        setIsRemovingBackground(true)

        try {
            const response = await axiosInstance.post(
                '/design-mode/nano-banana/remove-background',
                {
                    session_id: sessionId,
                    presentation_name: presentationName,
                    slide_number: activeSlide.slideNumber,
                    image_url: activeSlide.imageUrl
                },
                { signal: controller.signal }
            )

            if (response.data?.success) {
                await loadVersions()

                const newImageUrl = response.data.new_image_url
                if (newImageUrl) {
                    updateSlideImage(activeSlide.slideNumber, newImageUrl)
                    redetectSlide(activeSlide.slideNumber, newImageUrl)
                }

                toast.success(
                    t(
                        'designMode.backgroundRemoved',
                        'Background removed successfully'
                    )
                )
            } else {
                toast.error(
                    response.data?.error ||
                    t(
                        'designMode.backgroundRemovalFailed',
                        'Background removal failed'
                    )
                )
            }
        } catch (err: unknown) {
            if (
                err instanceof Error &&
                (err.name === 'CanceledError' || err.name === 'AbortError')
            )
                return
            console.error('[NanoBanana] Background removal error:', err)
            toast.error(
                t(
                    'designMode.backgroundRemovalFailed',
                    'Failed to remove background'
                )
            )
        } finally {
            setIsRemovingBackground(false)
            bgRemovalAbortRef.current = null
        }
    }, [
        activeSlide,
        sessionId,
        presentationName,
        loadVersions,
        updateSlideImage,
        redetectSlide,
        t
    ])

    // Handle version revert
    const handleVersionSelect = useCallback(
        async (versionId: string) => {
            const newImageUrl = await revertToVersion(versionId)
            if (newImageUrl && activeSlide) {
                updateSlideImage(activeSlide.slideNumber, newImageUrl)
                redetectSlide(activeSlide.slideNumber, newImageUrl)
                toast.success(
                    t(
                        'designMode.versionReverted',
                        'Reverted to previous version'
                    )
                )
            }
            return newImageUrl
        },
        [revertToVersion, activeSlide, updateSlideImage, redetectSlide, t]
    )

    // Get detection state for current slide
    const currentDetectionState = activeSlide
        ? slideStates.get(activeSlide.slideNumber) || null
        : null

    // Get detected components for inspector
    const detectedComponents = currentDetectionState?.components || []

    // Active slide instructions
    const activeInstructions = activeSlide
        ? getInstructions(activeSlide.slideNumber)
        : []

    const isAnyRegenerating =
        regeneratingSlides.size > 0 || isRemovingBackground

    // Portal target for inspector panel (rendered in ChatBox's "Live edit" tab)
    const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null)

    useEffect(() => {
        const findPortal = () => {
            const el = document.getElementById('nano-banana-inspector-root')
            setPortalTarget(el)
        }
        findPortal()
        const timer = setTimeout(findPortal, 100)
        return () => clearTimeout(timer)
    }, [])

    // Wrap addInstruction to bind to active slide number
    const handleAddInstruction = useCallback(
        (params: Parameters<typeof addInstruction>[1]) => {
            if (!activeSlide) return ''
            return addInstruction(activeSlide.slideNumber, params)
        },
        [addInstruction, activeSlide]
    )

    // Wrap removeInstruction to bind to active slide number
    const handleRemoveInstruction = useCallback(
        (id: string) => {
            if (!activeSlide) return
            removeInstruction(activeSlide.slideNumber, id)
        },
        [removeInstruction, activeSlide]
    )

    const inspectorElement = (
        <NanoBananaInspector
            selection={currentSelection}
            detectedComponents={detectedComponents}
            instructions={activeInstructions}
            onAddInstruction={handleAddInstruction}
            onRemoveInstruction={handleRemoveInstruction}
            disabled={isAnyRegenerating}
        />
    )

    return (
        <div
            className={cn(
                'flex flex-col h-full min-w-0 overflow-hidden',
                className
            )}
        >
            {/* Toolbar */}
            <NanoBananaToolbar
                selectionMode={selectionMode}
                onSelectionModeChange={setSelectionMode}
                instructionCount={totalInstructionCount}
                onApplyChanges={handleApplyChanges}
                onRemoveBackground={handleRemoveBackground}
                isRegenerating={isAnyRegenerating}
                versions={versions}
                currentVersionId={currentVersionId}
                onVersionSelect={handleVersionSelect}
                isReverting={isReverting}
                disabled={isAnyRegenerating}
            />

            {/* Main content area - scrollable slides viewer (full width) */}
            <div className="relative slides-viewer flex-1 max-h-[calc(100vh-120px)] overflow-y-auto overflow-x-hidden bg-neutral-200 dark:bg-neutral-950">
                <div className="slides-container flex flex-col gap-8 items-center p-5">
                    {localSlides.map((slide, index) => {
                        const slideDetectionState =
                            slideStates.get(slide.slideNumber) || null
                        const isActive = index === activeSlideIndex
                        const slideInstructions = getInstructions(
                            slide.slideNumber
                        )

                        return (
                            <div
                                key={slide.slideNumber}
                                className={cn(
                                    'w-full max-w-[1080px] cursor-pointer transition-all',
                                    isActive
                                        ? 'ring-2 ring-sky-500 ring-offset-2 ring-offset-neutral-200 dark:ring-offset-neutral-950'
                                        : 'hover:ring-2 hover:ring-neutral-400 hover:ring-offset-2 hover:ring-offset-neutral-200 dark:hover:ring-offset-neutral-950'
                                )}
                                onClick={() =>
                                    handleSlideClick(index, slide)
                                }
                            >
                                <NanoBananaSlidePanel
                                    slideNumber={slide.slideNumber}
                                    imageUrl={slide.imageUrl}
                                    detectionState={slideDetectionState}
                                    selectionMode={
                                        isActive ? selectionMode : 'spot'
                                    }
                                    currentSelection={
                                        isActive ? currentSelection : null
                                    }
                                    onSelectionChange={
                                        isActive ? setSelection : () => { }
                                    }
                                    onDetect={() =>
                                        detectSlide(
                                            slide.slideNumber,
                                            slide.imageUrl
                                        )
                                    }
                                    onRetry={() =>
                                        retrySlide(slide.slideNumber)
                                    }
                                    committedInstructions={slideInstructions}
                                    isRegenerating={regeneratingSlides.has(
                                        slide.slideNumber
                                    )}
                                />
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* Inspector panel - portaled to ChatBox "Live edit" tab */}
            {portalTarget
                ? createPortal(inspectorElement, portalTarget)
                : null}
        </div>
    )
}
