/**
 * Hook for managing edit instructions in nano banana design mode.
 * Instructions are queued per-slide and applied when the user clicks "Apply Changes".
 *
 * Manages instructions for ALL slides simultaneously via a Map<slideNumber, Instruction[]>,
 * so switching between slides preserves each slide's independent instruction list.
 *
 * Local-only state — no database persistence. On design mode toggle-off,
 * the component unmounts and all instructions are discarded.
 */

import { useState, useCallback, useMemo } from 'react'
import type { Instruction, Selection, InstructionType } from './types'

export function useNanoBananaInstructions() {
    const [instructionMap, setInstructionMap] = useState<
        Map<number, Instruction[]>
    >(new Map())

    const getInstructions = useCallback(
        (slideNumber: number): Instruction[] => {
            return instructionMap.get(slideNumber) || []
        },
        [instructionMap]
    )

    const addInstruction = useCallback(
        (
            slideNumber: number,
            params: {
                selection: Selection
                instruction_type: InstructionType
                new_text?: string
                ai_prompt?: string
            }
        ) => {
            const newInstruction: Instruction = {
                id: `inst-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                selection: params.selection,
                instruction_type: params.instruction_type,
                new_text: params.new_text,
                ai_prompt: params.ai_prompt,
                timestamp: Date.now()
            }

            setInstructionMap((prev) => {
                const next = new Map(prev)
                const existing = prev.get(slideNumber) || []
                next.set(slideNumber, [...existing, newInstruction])
                return next
            })

            return newInstruction.id
        },
        []
    )

    const removeInstruction = useCallback(
        (slideNumber: number, id: string) => {
            setInstructionMap((prev) => {
                const next = new Map(prev)
                const existing = prev.get(slideNumber) || []
                next.set(
                    slideNumber,
                    existing.filter((inst) => inst.id !== id)
                )
                return next
            })
        },
        []
    )

    const clearSlideInstructions = useCallback((slideNumber: number) => {
        setInstructionMap((prev) => {
            const next = new Map(prev)
            next.set(slideNumber, [])
            return next
        })
    }, [])

    const clearAllInstructions = useCallback(() => {
        setInstructionMap(new Map())
    }, [])

    const slidesWithInstructions = useMemo(() => {
        return [...instructionMap.entries()]
            .filter(([, insts]) => insts.length > 0)
            .map(([num]) => num)
    }, [instructionMap])

    const totalInstructionCount = useMemo(() => {
        return [...instructionMap.values()].reduce(
            (sum, insts) => sum + insts.length,
            0
        )
    }, [instructionMap])

    return {
        getInstructions,
        addInstruction,
        removeInstruction,
        clearSlideInstructions,
        clearAllInstructions,
        slidesWithInstructions,
        totalInstructionCount,
        hasAnyInstructions: totalInstructionCount > 0
    }
}
