import { useEffect, useRef, useState, type RefObject } from 'react'

export function useSlideDeckScale(options: {
    viewportRef: RefObject<HTMLElement | null>
    deckWidth?: number
    minUnscaledHeight?: number
}) {
    const { viewportRef, deckWidth = 1280, minUnscaledHeight = 240 } = options

    const resizeObserverRef = useRef<ResizeObserver | null>(null)
    const [scale, setScale] = useState(1)
    const [iframeUnscaledHeight, setIframeUnscaledHeight] = useState(720)

    useEffect(() => {
        const el = viewportRef.current
        if (!el) return

        const update = () => {
            const width = el.clientWidth
            const height = el.clientHeight
            if (width <= 0 || height <= 0) return

            const nextScale = Math.min(1, width / deckWidth)
            setScale(nextScale)
            setIframeUnscaledHeight(
                Math.max(minUnscaledHeight, Math.ceil(height / nextScale))
            )
        }

        update()

        if (typeof ResizeObserver !== 'undefined') {
            resizeObserverRef.current?.disconnect()
            resizeObserverRef.current = new ResizeObserver(update)
            resizeObserverRef.current.observe(el)
        }

        return () => {
            resizeObserverRef.current?.disconnect()
            resizeObserverRef.current = null
        }
    }, [viewportRef, deckWidth, minUnscaledHeight])

    return { scale, iframeUnscaledHeight }
}
