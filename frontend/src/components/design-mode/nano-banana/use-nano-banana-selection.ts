/**
 * Hook for managing selection state in nano banana design mode.
 * Handles component, spot, and box selections.
 */

import { useState, useCallback } from 'react'
import type { Selection, SelectionMode, DetectedComponent } from './types'

export function useNanoBananaSelection() {
    const [selectionMode, setSelectionMode] =
        useState<SelectionMode>('component')
    const [currentSelection, setCurrentSelection] = useState<Selection | null>(
        null
    )

    const setSelection = useCallback((selection: Selection | null) => {
        setCurrentSelection(selection)
    }, [])

    const clearSelection = useCallback(() => {
        setCurrentSelection(null)
    }, [])

    const selectComponent = useCallback((componentId: string) => {
        setCurrentSelection({
            type: 'component',
            component_id: componentId
        })
    }, [])

    const selectSpot = useCallback((x: number, y: number) => {
        setCurrentSelection({
            type: 'spot',
            spot_x: x,
            spot_y: y
        })
    }, [])

    const selectBox = useCallback(
        (x: number, y: number, width: number, height: number) => {
            setCurrentSelection({
                type: 'box',
                box: { x, y, width, height }
            })
        },
        []
    )

    // Get the selected component details if a component is selected
    const getSelectedComponent = useCallback(
        (components: DetectedComponent[]): DetectedComponent | null => {
            if (
                currentSelection?.type !== 'component' ||
                !currentSelection.component_id
            ) {
                return null
            }
            return (
                components.find(
                    (c) => c.design_id === currentSelection.component_id
                ) || null
            )
        },
        [currentSelection]
    )

    return {
        selectionMode,
        setSelectionMode,
        currentSelection,
        setSelection,
        clearSelection,
        selectComponent,
        selectSpot,
        selectBox,
        getSelectedComponent
    }
}
