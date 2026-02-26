/**
 * Hook for calling the nano banana detection API per slide.
 * Manages detection state for each slide independently.
 *
 * Each slide fires its own API call in parallel — no need to wait
 * for slide 1 to finish before detecting slide 2.
 *
 * Supports cancellation via AbortController so all in-flight
 * requests can be aborted when design mode is toggled off.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import axiosInstance from '@/lib/axios'
import type { SlideDetectionState, NanoBananaSlideInfo } from './types'

interface UseNanoBananaDetectionOptions {
    sessionId: string
    presentationName: string
}

export function useNanoBananaDetection({
    sessionId,
    presentationName
}: UseNanoBananaDetectionOptions) {
    const [slideStates, setSlideStates] = useState<
        Map<number, SlideDetectionState>
    >(new Map())

    // Track slides that are currently being detected
    const detectingRef = useRef<Set<number>>(new Set())
    // Track slides that have been processed
    const processedRef = useRef<Set<number>>(new Set())
    // Track if component is mounted
    const isMountedRef = useRef(true)
    // Track AbortControllers per slide for cancellation
    const abortControllersRef = useRef<Map<number, AbortController>>(new Map())

    // Cleanup on unmount — cancel all in-flight requests
    useEffect(() => {
        isMountedRef.current = true
        return () => {
            isMountedRef.current = false
            // Abort all in-flight detection requests
            for (const controller of abortControllersRef.current.values()) {
                controller.abort()
            }
            abortControllersRef.current.clear()
            detectingRef.current.clear()
            processedRef.current.clear()
        }
    }, [])

    const detectSlide = useCallback(
        async (slideNumber: number, imageUrl: string) => {
            // Skip if unmounted, already processed, or currently detecting
            if (!isMountedRef.current) return
            if (processedRef.current.has(slideNumber)) return
            if (detectingRef.current.has(slideNumber)) return

            detectingRef.current.add(slideNumber)

            // Create AbortController for this request
            const controller = new AbortController()
            abortControllersRef.current.set(slideNumber, controller)

            // Set loading state
            if (isMountedRef.current) {
                setSlideStates((prev) => {
                    const next = new Map(prev)
                    next.set(slideNumber, {
                        slideNumber,
                        imageUrl,
                        status: 'loading',
                        components: [],
                        overlayHtml: null,
                        imageWidth: 1280,
                        imageHeight: 720,
                        error: null
                    })
                    return next
                })
            }

            try {
                const response = await axiosInstance.post(
                    '/slides/nano-banana/detect',
                    {
                        session_id: sessionId,
                        presentation_name: presentationName,
                        slide_number: slideNumber,
                        image_url: imageUrl
                    },
                    { signal: controller.signal }
                )

                if (!isMountedRef.current) return

                if (!response.data?.success) {
                    throw new Error(response.data?.error || 'Detection failed')
                }

                setSlideStates((prev) => {
                    const next = new Map(prev)
                    next.set(slideNumber, {
                        slideNumber,
                        imageUrl,
                        status: 'ready',
                        components: response.data?.components || [],
                        overlayHtml: response.data?.overlay_html || null,
                        imageWidth: response.data?.image_width || 1280,
                        imageHeight: response.data?.image_height || 720,
                        error: null
                    })
                    return next
                })

                processedRef.current.add(slideNumber)
            } catch (err: unknown) {
                // Silently ignore aborted requests
                if (err instanceof Error && err.name === 'CanceledError') return
                if (err instanceof DOMException && err.name === 'AbortError')
                    return
                if (!isMountedRef.current) return

                const errorMsg =
                    err instanceof Error ? err.message : 'Detection failed'

                setSlideStates((prev) => {
                    const next = new Map(prev)
                    next.set(slideNumber, {
                        slideNumber,
                        imageUrl,
                        status: 'error',
                        components: [],
                        overlayHtml: null,
                        imageWidth: 1280,
                        imageHeight: 720,
                        error: errorMsg
                    })
                    return next
                })

                processedRef.current.add(slideNumber)
            } finally {
                detectingRef.current.delete(slideNumber)
                abortControllersRef.current.delete(slideNumber)
            }
        },
        [sessionId, presentationName]
    )

    const detectAllSlides = useCallback(
        (slides: NanoBananaSlideInfo[]) => {
            if (!isMountedRef.current) return

            const toDetect = slides.filter(
                (s) =>
                    !processedRef.current.has(s.slideNumber) &&
                    !detectingRef.current.has(s.slideNumber)
            )

            for (const slide of toDetect) {
                void detectSlide(slide.slideNumber, slide.imageUrl)
            }
        },
        [detectSlide]
    )

    const retrySlide = useCallback(
        (slideNumber: number) => {
            const state = slideStates.get(slideNumber)
            if (state && isMountedRef.current) {
                // Abort any in-flight detection for this slide
                const existing = abortControllersRef.current.get(slideNumber)
                if (existing) {
                    existing.abort()
                    abortControllersRef.current.delete(slideNumber)
                }
                processedRef.current.delete(slideNumber)
                detectingRef.current.delete(slideNumber)
                void detectSlide(slideNumber, state.imageUrl)
            }
        },
        [slideStates, detectSlide]
    )

    // Re-detect a slide with a new image URL (e.g. after regeneration)
    const redetectSlide = useCallback(
        (slideNumber: number, newImageUrl: string) => {
            if (!isMountedRef.current) return
            // Abort any in-flight detection for this slide to prevent race conditions
            const existing = abortControllersRef.current.get(slideNumber)
            if (existing) {
                existing.abort()
                abortControllersRef.current.delete(slideNumber)
            }
            processedRef.current.delete(slideNumber)
            detectingRef.current.delete(slideNumber)
            void detectSlide(slideNumber, newImageUrl)
        },
        [detectSlide]
    )

    // Cancel all in-flight detection requests and reset state
    const cancelAll = useCallback(() => {
        for (const controller of abortControllersRef.current.values()) {
            controller.abort()
        }
        abortControllersRef.current.clear()
        detectingRef.current.clear()
        processedRef.current.clear()
        setSlideStates(new Map())
    }, [])

    const isDetecting = detectingRef.current.size > 0

    return {
        slideStates,
        detectSlide,
        detectAllSlides,
        retrySlide,
        redetectSlide,
        cancelAll,
        isDetecting
    }
}
