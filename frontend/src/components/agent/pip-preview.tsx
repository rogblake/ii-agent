import { useCallback, useEffect, useRef, useState } from 'react'
import { GripHorizontal, Zap, ChevronDown } from 'lucide-react'
import { Icon } from '../ui/icon'
import { cn } from '@/lib/utils'

interface PiPPreviewProps {
    url: string
    isMobile?: boolean
    onClose: () => void
}

const PiPPreview = ({ url, isMobile, onClose }: PiPPreviewProps) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const [position, setPosition] = useState({ x: 0, y: 0 })
    const isDragging = useRef(false)
    const hasDragged = useRef(false)
    const dragStart = useRef({ x: 0, y: 0 })

    const handlePointerDown = useCallback(
        (e: React.PointerEvent) => {
            isDragging.current = true
            hasDragged.current = false
            dragStart.current = {
                x: e.clientX - position.x,
                y: e.clientY - position.y
            }
            ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
        },
        [position]
    )

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!isDragging.current) return
        hasDragged.current = true
        setPosition({
            x: e.clientX - dragStart.current.x,
            y: e.clientY - dragStart.current.y
        })
    }, [])

    const handlePointerUp = useCallback(() => {
        isDragging.current = false
    }, [])

    // Clamp position so PiP stays within viewport
    useEffect(() => {
        const el = containerRef.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth
        const vh = window.innerHeight
        let { x, y } = position
        let clamped = false

        if (rect.left < 0) {
            x -= rect.left
            clamped = true
        }
        if (rect.top < 0) {
            y -= rect.top
            clamped = true
        }
        if (rect.right > vw) {
            x -= rect.right - vw
            clamped = true
        }
        if (rect.bottom > vh) {
            y -= rect.bottom - vh
            clamped = true
        }
        if (clamped) setPosition({ x, y })
    }, [position])

    return (
        <div
            ref={containerRef}
            className="fixed bottom-6 left-6 z-50 flex flex-col"
            style={{
                transform: `translate(${position.x}px, ${position.y}px)`
            }}
        >
            {/* Header toolbar */}
            <div
                className={cn(
                    'flex items-center justify-between rounded-t-xl bg-[#2a2a2e] px-3 py-2 select-none',
                    isMobile ? 'w-[200px]' : 'w-[320px]'
                )}
            >
                {/* Drag handle */}
                <div
                    className="cursor-grab active:cursor-grabbing touch-none"
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={handlePointerUp}
                >
                    <GripHorizontal className="size-4 text-gray-400" />
                </div>

                {/* Label */}
                <div className="flex items-center gap-1 text-xs text-gray-300 font-medium">
                    <Zap className="size-3" />
                    <span>{isMobile ? 'App' : 'Web'}</span>
                    <ChevronDown className="size-3 text-gray-500" />
                </div>

                {/* Close PiP button */}
                <button
                    className="cursor-pointer"
                    onClick={(e) => {
                        e.stopPropagation()
                        onClose()
                    }}
                >
                    <Icon
                        name="maximize"
                        className="size-4 fill-gray-400 hover:fill-white transition-colors"
                    />
                </button>
            </div>

            {/* Preview container – iframe is rendered at full size then scaled down */}
            <div
                className={cn(
                    'rounded-b-xl overflow-hidden shadow-2xl border border-t-0 border-gray-700 bg-white',
                    isMobile
                        ? 'w-[200px] aspect-[9/19.5]'
                        : 'w-[320px] aspect-video'
                )}
            >
                <iframe
                    src={url}
                    className="border-0 origin-top-left"
                    title="Preview"
                    style={
                        isMobile
                            ? {
                                  width: '390px',
                                  height: '845px',
                                  transform: `scale(${200 / 390})`,
                              }
                            : {
                                  width: '1280px',
                                  height: '720px',
                                  transform: 'scale(0.25)',
                              }
                    }
                />
            </div>
        </div>
    )
}

export default PiPPreview
