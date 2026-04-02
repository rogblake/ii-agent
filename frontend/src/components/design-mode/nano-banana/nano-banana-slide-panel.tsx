/**
 * Nano Banana Slide Panel Component
 *
 * Displays a single slide with its image and interactive selection overlay.
 * Handles loading, error, and ready states.
 */

import { useCallback } from 'react'
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { SelectionOverlay } from './selection-overlay'
import type {
    SlideDetectionState,
    SelectionMode,
    Selection,
    Instruction
} from './types'

interface NanoBananaSlidePanelProps {
    slideNumber: number
    imageUrl: string
    detectionState: SlideDetectionState | null
    selectionMode: SelectionMode
    currentSelection: Selection | null
    onSelectionChange: (selection: Selection | null) => void
    onDetect: () => void
    onRetry: () => void
    className?: string
    /** Committed instructions to show their selections on the slide */
    committedInstructions?: Instruction[]
    /** Whether this slide is being regenerated */
    isRegenerating?: boolean
}

export function NanoBananaSlidePanel({
    slideNumber,
    imageUrl,
    detectionState,
    selectionMode,
    currentSelection,
    onSelectionChange,
    onDetect,
    onRetry,
    className,
    committedInstructions = [],
    isRegenerating = false
}: NanoBananaSlidePanelProps) {
    const { t } = useTranslation()

    const status = detectionState?.status || 'idle'
    const components = detectionState?.components || []

    // Trigger detection on first render if not done
    const handleImageLoad = useCallback(() => {
        if (status === 'idle') {
            onDetect()
        }
    }, [status, onDetect])

    return (
        <div className={cn('relative w-full', className)}>
            {/* Slide container — image-driven sizing, overlay matches exactly */}
            <div className="relative bg-black rounded-xl overflow-hidden shadow-lg w-full">
                {/* Slide image drives the container height */}
                <img
                    src={imageUrl}
                    alt={`Slide ${slideNumber}`}
                    className="block w-full h-auto"
                    onLoad={handleImageLoad}
                    draggable={false}
                />

                {/* Loading overlay for detection */}
                {status === 'loading' && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/50 text-white">
                        <Loader2 className="w-8 h-8 animate-spin mb-2" />
                        <span className="text-sm">
                            {t(
                                'designMode.detectingComponents',
                                'Detecting components...'
                            )}
                        </span>
                    </div>
                )}

                {/* Loading overlay for regeneration */}
                {isRegenerating && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 text-white z-20">
                        <Loader2 className="w-10 h-10 animate-spin mb-3" />
                        <span className="text-sm font-medium">
                            {t(
                                'designMode.applyingChanges',
                                'Applying changes...'
                            )}
                        </span>
                    </div>
                )}

                {/* Error overlay */}
                {status === 'error' && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 text-white">
                        <AlertCircle className="w-8 h-8 text-red-400 mb-2" />
                        <span className="text-sm mb-3">
                            {detectionState?.error ||
                                t(
                                    'designMode.detectionFailed',
                                    'Detection failed'
                                )}
                        </span>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onRetry}
                            className="gap-1.5"
                        >
                            <RefreshCw className="h-4 w-4" />
                            {t('common.retry', 'Retry')}
                        </Button>
                    </div>
                )}

                {/* Selection overlay (only when ready) — absolute inset-0 matches image exactly */}
                {status === 'ready' && (
                    <SelectionOverlay
                        selectionMode={selectionMode}
                        components={components}
                        currentSelection={currentSelection}
                        onSelectionChange={onSelectionChange}
                        committedInstructions={committedInstructions}
                    />
                )}
            </div>

            {/* Slide number badge */}
            <div className="absolute right-4 bottom-4 text-xs h-7 px-4 flex justify-center items-center bg-black/80 text-white rounded-full z-20">
                <span>{slideNumber}</span>
            </div>

            {/* Component count badge (when ready) */}
            {status === 'ready' && components.length > 0 && (
                <div className="absolute left-4 bottom-4 text-xs h-7 px-3 flex items-center gap-1.5 bg-sky-500/90 text-white rounded-full z-20">
                    <span className="font-medium">{components.length}</span>
                    <span>
                        {components.length === 1 ? 'component' : 'components'}
                    </span>
                </div>
            )}
        </div>
    )
}
