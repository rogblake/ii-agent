/**
 * Nano Banana Inspector Panel
 *
 * Right-side panel for editing selected elements.
 * Shows text editor for text components and AI modification input.
 */

import { useState, useCallback, useEffect } from 'react'
import { Sparkles, X, Type, Wand2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type {
    Selection,
    Instruction,
    DetectedComponent,
    InstructionType
} from './types'

// Text component types that may have editable text
const TEXT_COMPONENT_TYPES = new Set([
    'title',
    'subtitle',
    'text_block',
    'bullet_list',
    'footer',
    'header',
    'text'
])

interface NanoBananaInspectorProps {
    selection: Selection | null
    detectedComponents: DetectedComponent[]
    instructions: Instruction[]
    onAddInstruction: (params: {
        selection: Selection
        instruction_type: InstructionType
        new_text?: string
        ai_prompt?: string
    }) => string
    onRemoveInstruction: (id: string) => void
    disabled?: boolean
}

export function NanoBananaInspector({
    selection,
    detectedComponents,
    instructions,
    onAddInstruction,
    onRemoveInstruction,
    disabled = false
}: NanoBananaInspectorProps) {
    const { t } = useTranslation()
    const [textValue, setTextValue] = useState('')
    const [aiPrompt, setAiPrompt] = useState('')

    // Get selected component details
    const selectedComponent =
        selection?.type === 'component' && selection.component_id
            ? detectedComponents.find(
                (c) => c.design_id === selection.component_id
            )
            : null

    // Check if selection has text content
    const hasTextContent =
        selectedComponent &&
        (selectedComponent.text_content != null ||
            TEXT_COMPONENT_TYPES.has(selectedComponent.component_type))

    // Prefill text value when selecting a text component
    useEffect(() => {
        if (selectedComponent?.text_content) {
            setTextValue(selectedComponent.text_content)
        } else {
            setTextValue('')
        }
    }, [selectedComponent])

    // Handle adding text edit instruction
    const handleAddTextEdit = useCallback(() => {
        if (!selection || !textValue.trim()) return
        onAddInstruction({
            selection,
            instruction_type: 'text_edit',
            new_text: textValue.trim()
        })
        setTextValue('')
    }, [selection, textValue, onAddInstruction])

    // Handle adding AI modification instruction
    const handleAddAiModify = useCallback(() => {
        if (!selection || !aiPrompt.trim()) return
        onAddInstruction({
            selection,
            instruction_type: 'ai_modify',
            ai_prompt: aiPrompt.trim()
        })
        setAiPrompt('')
    }, [selection, aiPrompt, onAddInstruction])

    // Get selection type label
    const getSelectionLabel = () => {
        if (!selection) return null

        switch (selection.type) {
            case 'component':
                return selectedComponent?.component_type || 'Component'
            case 'spot':
                return 'Point Selection'
            case 'box':
                return 'Region Selection'
            default:
                return 'Selection'
        }
    }

    // Get instruction description
    const getInstructionDescription = (inst: Instruction) => {
        if (inst.instruction_type === 'text_edit') {
            const text = inst.new_text || ''
            return text.length > 50 ? `${text.slice(0, 47)}...` : text
        }
        if (inst.instruction_type === 'ai_modify') {
            const prompt = inst.ai_prompt || ''
            return prompt.length > 50 ? `${prompt.slice(0, 47)}...` : prompt
        }
        if (inst.instruction_type === 'remove_background') {
            return 'Remove background'
        }
        return 'Unknown'
    }

    return (
        <div className="h-full bg-neutral-50 dark:bg-neutral-900 flex flex-col">
            {/* Header */}
            <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                    {t('designMode.inspector', 'Inspector')}
                </h3>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* No selection state */}
                {!selection && (
                    <div className="text-sm text-neutral-500 dark:text-neutral-400">
                        <p className="mb-2">
                            Select a component, click a spot, or drag a box to
                            start editing.
                        </p>
                        <ul className="text-xs space-y-1 list-disc list-inside">
                            <li>
                                <strong>Component mode:</strong> Click on
                                detected elements
                            </li>
                            <li>
                                <strong>Spot mode:</strong> Click anywhere to
                                mark a point
                            </li>
                            <li>
                                <strong>Box mode:</strong> Drag to select a
                                region
                            </li>
                        </ul>
                    </div>
                )}

                {/* Selection info */}
                {selection && (
                    <>
                        {/* Selection type badge */}
                        <div className="flex items-center gap-2">
                            <span className="text-xs px-2 py-1 rounded-full bg-sky-100 dark:bg-sky-900 text-sky-700 dark:text-sky-300 font-medium">
                                {getSelectionLabel()}
                            </span>
                            {selectedComponent?.label && (
                                <span className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                                    {selectedComponent.label}
                                </span>
                            )}
                        </div>

                        {/* Text content editor (only for text components) */}
                        {hasTextContent && (
                            <div className="space-y-2">
                                <div className="flex items-center gap-2">
                                    <Type className="h-4 w-4 text-neutral-500" />
                                    <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                                        {t(
                                            'designMode.textContent',
                                            'Text Content'
                                        )}
                                    </label>
                                </div>

                                {/* Editable text input (prefilled with current text) */}
                                <Textarea
                                    value={textValue}
                                    onChange={(e) =>
                                        setTextValue(e.target.value)
                                    }
                                    placeholder={t(
                                        'designMode.enterNewText',
                                        'Enter new text...'
                                    )}
                                    rows={3}
                                    className="text-sm resize-none"
                                    disabled={disabled}
                                    onKeyDown={(e) => {
                                        if (
                                            e.key === 'Enter' &&
                                            !e.shiftKey &&
                                            !e.nativeEvent.isComposing
                                        ) {
                                            e.preventDefault()
                                            handleAddTextEdit()
                                        }
                                    }}
                                />
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={handleAddTextEdit}
                                    disabled={
                                        disabled ||
                                        !textValue.trim() ||
                                        textValue === selectedComponent?.text_content
                                    }
                                    className="w-full"
                                >
                                    <Type className="h-3.5 w-3.5 mr-1.5" />
                                    {t('designMode.updateText', 'Update Text')}
                                </Button>
                            </div>
                        )}

                        {/* AI modification input */}
                        <div className="space-y-2 pt-3 border-t border-neutral-200 dark:border-neutral-800">
                            <div className="flex items-center gap-2">
                                <Sparkles className="h-4 w-4 text-purple-500" />
                                <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                                    {t(
                                        'designMode.aiModification',
                                        'AI Modification'
                                    )}
                                </label>
                            </div>

                            <div className="relative">
                                <Textarea
                                    value={aiPrompt}
                                    onChange={(e) =>
                                        setAiPrompt(e.target.value)
                                    }
                                    placeholder={t(
                                        'designMode.describeChange',
                                        'Describe what to change... (e.g., "change color to red", "make text bold")'
                                    )}
                                    rows={3}
                                    className="text-sm resize-none pr-10"
                                    disabled={disabled}
                                    onKeyDown={(e) => {
                                        if (
                                            e.key === 'Enter' &&
                                            !e.shiftKey &&
                                            !e.nativeEvent.isComposing
                                        ) {
                                            e.preventDefault()
                                            handleAddAiModify()
                                        }
                                    }}
                                />
                                <button
                                    type="button"
                                    className={cn(
                                        'absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-full',
                                        'bg-purple-500 hover:bg-purple-600 transition-colors',
                                        'disabled:opacity-50 disabled:cursor-not-allowed'
                                    )}
                                    disabled={disabled || !aiPrompt.trim()}
                                    onClick={handleAddAiModify}
                                    title={t('common.add', 'Add')}
                                >
                                    <Wand2 className="h-4 w-4 text-white" />
                                </button>
                            </div>
                        </div>
                    </>
                )}

                {/* Pending instructions list */}
                {instructions.length > 0 && (
                    <div className="pt-3 border-t border-neutral-200 dark:border-neutral-800">
                        <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                                {t('designMode.pendingChanges', 'Pending Changes')}
                            </h4>
                            <span className="text-xs px-1.5 py-0.5 rounded-full bg-sky-500 text-white font-medium">
                                {instructions.length}
                            </span>
                        </div>

                        <div className="space-y-2">
                            {instructions.map((inst) => (
                                <div
                                    key={inst.id}
                                    className="group flex items-start gap-2 p-2 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700"
                                >
                                    <div className="flex-shrink-0 mt-0.5">
                                        {inst.instruction_type ===
                                            'text_edit' ? (
                                            <Type className="h-3.5 w-3.5 text-neutral-400" />
                                        ) : inst.instruction_type ===
                                            'ai_modify' ? (
                                            <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                                        ) : (
                                            <Wand2 className="h-3.5 w-3.5 text-neutral-400" />
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-neutral-600 dark:text-neutral-300 break-words">
                                            {getInstructionDescription(inst)}
                                        </p>
                                        <p className="text-[10px] text-neutral-400 mt-0.5">
                                            {inst.selection.type === 'component'
                                                ? 'Component'
                                                : inst.selection.type === 'spot'
                                                    ? 'Point'
                                                    : 'Region'}
                                        </p>
                                    </div>
                                    <button
                                        type="button"
                                        className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                        onClick={() =>
                                            onRemoveInstruction(inst.id)
                                        }
                                        title={t('common.remove', 'Remove')}
                                    >
                                        <X className="h-4 w-4 text-neutral-400 hover:text-red-500" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
