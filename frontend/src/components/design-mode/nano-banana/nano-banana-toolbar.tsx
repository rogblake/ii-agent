/**
 * Nano Banana Toolbar Component
 *
 * Top toolbar with selection mode toggles, version selector,
 * and action buttons (remove background, apply changes).
 */

import { useTranslation } from 'react-i18next'
import {
    MousePointer2,
    Circle,
    Square,
    Eraser,
    Loader2,
    Check
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger
} from '@/components/ui/tooltip'
import { NanoBananaVersionSelector } from './nano-banana-version-selector'
import type { SelectionMode, SlideVersionInfo } from './types'

interface NanoBananaToolbarProps {
    selectionMode: SelectionMode
    onSelectionModeChange: (mode: SelectionMode) => void
    instructionCount: number
    onApplyChanges: () => void
    onRemoveBackground: () => void
    isRegenerating: boolean
    versions: SlideVersionInfo[]
    currentVersionId: string | null
    onVersionSelect: (versionId: string) => Promise<string | null>
    isReverting?: boolean
    disabled?: boolean
}

export function NanoBananaToolbar({
    selectionMode,
    onSelectionModeChange,
    instructionCount,
    onApplyChanges,
    onRemoveBackground,
    isRegenerating,
    versions,
    currentVersionId,
    onVersionSelect,
    isReverting = false,
    disabled = false
}: NanoBananaToolbarProps) {
    const { t } = useTranslation()

    const selectionModes: Array<{
        mode: SelectionMode
        icon: typeof MousePointer2
        label: string
        tooltip: string
    }> = [
            {
                mode: 'component',
                icon: MousePointer2,
                label: t('designMode.selectComponent', 'Component'),
                tooltip: t(
                    'designMode.selectComponentTooltip',
                    'Click on detected components'
                )
            },
            {
                mode: 'spot',
                icon: Circle,
                label: t('designMode.selectSpot', 'Spot'),
                tooltip: t(
                    'designMode.selectSpotTooltip',
                    'Click anywhere to mark a point'
                )
            },
            {
                mode: 'box',
                icon: Square,
                label: t('designMode.selectBox', 'Box'),
                tooltip: t(
                    'designMode.selectBoxTooltip',
                    'Drag to select a region'
                )
            }
        ]

    return (
        <div className="flex items-center justify-between flex-wrap gap-2 px-3 py-2 bg-neutral-100 dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-800 min-w-0">
            {/* Left side: Selection mode toggles */}
            <div className="flex items-center gap-1">
                <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400 mr-2">
                    {t('designMode.selectionMode', 'Selection:')}
                </span>

                <TooltipProvider delayDuration={300}>
                    <div className="flex items-center bg-white dark:bg-neutral-800 rounded-lg p-0.5 border border-neutral-200 dark:border-neutral-700">
                        {selectionModes.map(({ mode, icon: Icon, label, tooltip }) => (
                            <Tooltip key={mode}>
                                <TooltipTrigger asChild>
                                    <button
                                        type="button"
                                        className={cn(
                                            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors',
                                            selectionMode === mode
                                                ? 'bg-sky-500 text-white'
                                                : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-700'
                                        )}
                                        onClick={() => onSelectionModeChange(mode)}
                                        disabled={disabled || isRegenerating}
                                    >
                                        <Icon className="h-3.5 w-3.5" />
                                        <span className="hidden sm:inline">{label}</span>
                                    </button>
                                </TooltipTrigger>
                                <TooltipContent side="bottom">
                                    <p>{tooltip}</p>
                                </TooltipContent>
                            </Tooltip>
                        ))}
                    </div>
                </TooltipProvider>
            </div>

            {/* Right side: Actions */}
            <div className="flex items-center gap-2">
                {/* Version selector */}
                <NanoBananaVersionSelector
                    versions={versions}
                    currentVersionId={currentVersionId}
                    onVersionSelect={onVersionSelect}
                    isReverting={isReverting}
                    disabled={disabled || isRegenerating}
                />

                {/* Remove background button */}
                <TooltipProvider delayDuration={300}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onRemoveBackground}
                                disabled={disabled || isRegenerating}
                                className="gap-1.5"
                            >
                                <Eraser className="h-4 w-4" />
                                <span className="hidden sm:inline">
                                    {t('designMode.removeBackground', 'Remove BG')}
                                </span>
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                            <p>
                                {t(
                                    'designMode.removeBackgroundTooltip',
                                    'Remove the slide background'
                                )}
                            </p>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>

                {/* Apply changes button */}
                <Button
                    size="sm"
                    onClick={onApplyChanges}
                    disabled={
                        disabled || isRegenerating || instructionCount === 0
                    }
                    className={cn(
                        'gap-1.5 min-w-[120px]',
                        'bg-sky-500 hover:bg-sky-600 text-white'
                    )}
                >
                    {isRegenerating ? (
                        <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>
                                {t('designMode.regenerating', 'Regenerating...')}
                            </span>
                        </>
                    ) : (
                        <>
                            <Check className="h-4 w-4" />
                            <span>
                                {t('designMode.applyChanges', 'Apply Changes')}
                            </span>
                            {instructionCount > 0 && (
                                <span className="px-1.5 py-0.5 bg-white/20 rounded-full text-[10px] font-bold">
                                    {instructionCount}
                                </span>
                            )}
                        </>
                    )}
                </Button>
            </div>
        </div>
    )
}
