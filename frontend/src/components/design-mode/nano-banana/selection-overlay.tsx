/**
 * Selection Overlay Component
 *
 * Handles three selection modes:
 * - Component: Click on detected components
 * - Spot: Click anywhere to place a point marker
 * - Box: Drag to draw a rectangular selection
 */

import { useState, useRef, useCallback } from 'react'
import { cn } from '@/lib/utils'
import type {
    SelectionMode,
    Selection,
    BoundingBox,
    DetectedComponent,
    Instruction
} from './types'

interface SelectionOverlayProps {
    selectionMode: SelectionMode
    components: DetectedComponent[]
    currentSelection: Selection | null
    onSelectionChange: (selection: Selection | null) => void
    /** Committed instructions to show their selections on the slide */
    committedInstructions?: Instruction[]
}

export function SelectionOverlay({
    selectionMode,
    components,
    currentSelection,
    onSelectionChange,
    committedInstructions = []
}: SelectionOverlayProps) {
    const overlayRef = useRef<HTMLDivElement>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(
        null
    )
    const [dragBox, setDragBox] = useState<BoundingBox | null>(null)

    // Convert pixel position to percentage
    const toPercent = useCallback(
        (px: number, total: number) => Math.max(0, Math.min(100, (px / total) * 100)),
        []
    )

    // Get mouse position relative to overlay as percentages
    const getMousePosition = useCallback(
        (e: React.MouseEvent) => {
            const rect = overlayRef.current?.getBoundingClientRect()
            if (!rect) return { x: 0, y: 0 }

            const x = toPercent(e.clientX - rect.left, rect.width)
            const y = toPercent(e.clientY - rect.top, rect.height)
            return { x, y }
        },
        [toPercent]
    )

    // Handle click for spot selection
    const handleClick = useCallback(
        (e: React.MouseEvent) => {
            if (selectionMode !== 'spot' || isDragging) return

            const { x, y } = getMousePosition(e)
            onSelectionChange({
                type: 'spot',
                spot_x: x,
                spot_y: y
            })
        },
        [selectionMode, isDragging, getMousePosition, onSelectionChange]
    )

    // Handle drag for box selection
    const handleMouseDown = useCallback(
        (e: React.MouseEvent) => {
            if (selectionMode !== 'box') return

            const { x, y } = getMousePosition(e)
            setIsDragging(true)
            setDragStart({ x, y })
            setDragBox({ x, y, width: 0, height: 0 })
        },
        [selectionMode, getMousePosition]
    )

    const handleMouseMove = useCallback(
        (e: React.MouseEvent) => {
            if (!isDragging || !dragStart) return

            const { x: currentX, y: currentY } = getMousePosition(e)

            setDragBox({
                x: Math.min(dragStart.x, currentX),
                y: Math.min(dragStart.y, currentY),
                width: Math.abs(currentX - dragStart.x),
                height: Math.abs(currentY - dragStart.y)
            })
        },
        [isDragging, dragStart, getMousePosition]
    )

    const handleMouseUp = useCallback(() => {
        if (!isDragging || !dragBox) {
            setIsDragging(false)
            setDragStart(null)
            setDragBox(null)
            return
        }

        // Only create selection if box has meaningful size (> 2% in both dimensions)
        if (dragBox.width > 2 && dragBox.height > 2) {
            onSelectionChange({
                type: 'box',
                box: dragBox
            })
        }

        setIsDragging(false)
        setDragStart(null)
        setDragBox(null)
    }, [isDragging, dragBox, onSelectionChange])

    // Handle component click
    const handleComponentClick = useCallback(
        (e: React.MouseEvent, component: DetectedComponent) => {
            if (selectionMode !== 'component') return
            e.stopPropagation()

            onSelectionChange({
                type: 'component',
                component_id: component.design_id
            })
        },
        [selectionMode, onSelectionChange]
    )

    // Get cursor style based on mode
    const getCursorStyle = () => {
        switch (selectionMode) {
            case 'spot':
                return 'crosshair'
            case 'box':
                return 'crosshair'
            default:
                return 'default'
        }
    }

    return (
        <div
            ref={overlayRef}
            className="absolute inset-0 z-10"
            onClick={handleClick}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{ cursor: getCursorStyle() }}
        >
            {/* Render detected component boxes when in component mode */}
            {selectionMode === 'component' &&
                components.map((comp) => {
                    const isSelected =
                        currentSelection?.type === 'component' &&
                        currentSelection.component_id === comp.design_id

                    return (
                        <div
                            key={comp.design_id}
                            className={cn(
                                'absolute border-2 transition-all duration-150',
                                isSelected
                                    ? 'border-sky-500 bg-sky-500/20'
                                    : 'border-transparent hover:border-sky-400 hover:bg-sky-400/10'
                            )}
                            style={{
                                left: `${comp.bounding_box.x}%`,
                                top: `${comp.bounding_box.y}%`,
                                width: `${comp.bounding_box.width}%`,
                                height: `${comp.bounding_box.height}%`,
                                cursor: 'pointer'
                            }}
                            onClick={(e) => handleComponentClick(e, comp)}
                            title={comp.label}
                        />
                    )
                })}

            {/* Render spot selection marker */}
            {currentSelection?.type === 'spot' &&
                currentSelection.spot_x != null &&
                currentSelection.spot_y != null && (
                    <div
                        className="absolute w-5 h-5 -ml-2.5 -mt-2.5 rounded-full bg-sky-500 border-2 border-white shadow-lg pointer-events-none"
                        style={{
                            left: `${currentSelection.spot_x}%`,
                            top: `${currentSelection.spot_y}%`
                        }}
                    >
                        {/* Inner dot */}
                        <div className="absolute inset-1 rounded-full bg-white/50" />
                    </div>
                )}

            {/* Render box selection during drag */}
            {isDragging && dragBox && dragBox.width > 0 && dragBox.height > 0 && (
                <div
                    className="absolute border-2 border-dashed border-sky-500 bg-sky-500/10 pointer-events-none"
                    style={{
                        left: `${dragBox.x}%`,
                        top: `${dragBox.y}%`,
                        width: `${dragBox.width}%`,
                        height: `${dragBox.height}%`
                    }}
                />
            )}

            {/* Render completed box selection */}
            {!isDragging &&
                currentSelection?.type === 'box' &&
                currentSelection.box && (
                    <div
                        className="absolute border-2 border-sky-500 bg-sky-500/20 pointer-events-none"
                        style={{
                            left: `${currentSelection.box.x}%`,
                            top: `${currentSelection.box.y}%`,
                            width: `${currentSelection.box.width}%`,
                            height: `${currentSelection.box.height}%`
                        }}
                    >
                        {/* Corner handles */}
                        <div className="absolute -top-1 -left-1 w-2 h-2 bg-sky-500 rounded-full" />
                        <div className="absolute -top-1 -right-1 w-2 h-2 bg-sky-500 rounded-full" />
                        <div className="absolute -bottom-1 -left-1 w-2 h-2 bg-sky-500 rounded-full" />
                        <div className="absolute -bottom-1 -right-1 w-2 h-2 bg-sky-500 rounded-full" />
                    </div>
                )}

            {/* Render committed instruction markers (spots, boxes, and components from pending changes) */}
            {committedInstructions.map((instruction, idx) => {
                const sel = instruction.selection
                const ordinal = idx + 1

                // Number badge component
                const numberBadge = (
                    <div className="absolute -top-2.5 -left-2.5 w-5 h-5 rounded-full bg-sky-500 text-white text-[10px] font-bold flex items-center justify-center shadow-md z-10">
                        {ordinal}
                    </div>
                )

                // Render committed spot
                if (
                    sel.type === 'spot' &&
                    sel.spot_x != null &&
                    sel.spot_y != null
                ) {
                    return (
                        <div
                            key={instruction.id}
                            className="absolute w-5 h-5 -ml-2.5 -mt-2.5 pointer-events-none"
                            style={{
                                left: `${sel.spot_x}%`,
                                top: `${sel.spot_y}%`
                            }}
                        >
                            <div className="w-full h-full rounded-full bg-sky-500/70 border-2 border-white/70 shadow-md">
                                <div className="absolute inset-1 rounded-full bg-white/40" />
                            </div>
                            <div className="absolute -top-2 -right-2 w-4 h-4 rounded-full bg-sky-500 text-white text-[9px] font-bold flex items-center justify-center shadow-md">
                                {ordinal}
                            </div>
                        </div>
                    )
                }

                // Render committed box
                if (sel.type === 'box' && sel.box) {
                    return (
                        <div
                            key={instruction.id}
                            className="absolute border-2 border-sky-500/70 bg-sky-500/10 pointer-events-none"
                            style={{
                                left: `${sel.box.x}%`,
                                top: `${sel.box.y}%`,
                                width: `${sel.box.width}%`,
                                height: `${sel.box.height}%`
                            }}
                        >
                            {numberBadge}
                        </div>
                    )
                }

                // Render committed component
                if (sel.type === 'component' && sel.component_id) {
                    const comp = components.find(
                        (c) => c.design_id === sel.component_id
                    )
                    if (!comp) return null

                    return (
                        <div
                            key={instruction.id}
                            className="absolute border-2 border-sky-500/70 bg-sky-500/10 pointer-events-none"
                            style={{
                                left: `${comp.bounding_box.x}%`,
                                top: `${comp.bounding_box.y}%`,
                                width: `${comp.bounding_box.width}%`,
                                height: `${comp.bounding_box.height}%`
                            }}
                        >
                            {numberBadge}
                        </div>
                    )
                }

                return null
            })}
        </div>
    )
}
