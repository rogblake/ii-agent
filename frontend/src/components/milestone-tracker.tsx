import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Circle, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { Button } from './ui/button'
import { Icon } from './ui/icon'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from './ui/collapsible'
import {
    clearPlanModificationOptions,
    deleteMilestone,
    addMilestone,
    selectBuildMode,
    selectIsLoading,
    selectMilestoneProgress,
    selectMilestones,
    selectPlanSummary,
    selectSelectedMilestone,
    selectActiveSessionId,
    setBuildMode,
    setSelectedMilestoneId,
    updateMilestoneContent,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { BUILD_MODE, Milestone } from '@/typings'
import clsx from 'clsx'
import { sessionService } from '@/services/session.service'

const BUILD_MODE_STYLES: Record<BUILD_MODE, string> = {
    [BUILD_MODE.BUILD]: 'bg-sky-blue shadow-[0_8px_32px_rgba(56,189,248,0.25)]',
    [BUILD_MODE.DESIGN]: 'bg-orange shadow-[0_8px_32px_rgba(251,146,60,0.25)]',
    [BUILD_MODE.PLAN]:
        'bg-pewter dark:bg-mist shadow-[0_8px_32px_rgba(217,169,99,0.2)]',
    [BUILD_MODE.HELP]: 'bg-green-2 shadow-[0_8px_32px_rgba(52,211,153,0.25)]'
}

interface MilestoneTrackerProps {
    className?: string
    onBuildMilestone?: (
        milestone: Milestone,
        planContext: { summary: string; milestones: Milestone[] }
    ) => void
    onBuildAllMilestones?: (planContext: {
        summary: string
        milestones: Milestone[]
    }) => void
    onModifyPlan?: () => void
}

const MilestoneTracker = ({
    className,
    onBuildMilestone,
    onBuildAllMilestones,
    onModifyPlan
}: MilestoneTrackerProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const buildMode = useAppSelector(selectBuildMode)
    const milestones = useAppSelector(selectMilestones)
    const progress = useAppSelector(selectMilestoneProgress)
    const selectedMilestone = useAppSelector(selectSelectedMilestone)
    const planSummary = useAppSelector(selectPlanSummary)
    const isLoading = useAppSelector(selectIsLoading)
    const activeSessionId = useAppSelector(selectActiveSessionId)
    const [isOpen, setIsOpen] = useState(false)
    const [editingMilestoneId, setEditingMilestoneId] = useState<string | null>(
        null
    )
    const [editingValue, setEditingValue] = useState('')
    const containerRef = useRef<HTMLDivElement>(null)

    const canEditMilestones = buildMode === BUILD_MODE.PLAN && !isLoading

    const persistPlan = async (nextMilestones: Milestone[]) => {
        if (!activeSessionId) return
        try {
            await sessionService.updateSessionPlan(activeSessionId, {
                summary: planSummary ?? '',
                milestones: nextMilestones
            })
        } catch (err) {
            console.error('Failed to persist plan changes', err)
            toast.error(t('milestones.saveError'))
        }
    }

    const startEditing = (milestone: Milestone) => {
        setEditingMilestoneId(milestone.id)
        setEditingValue(milestone.content)
    }

    const stopEditing = () => {
        setEditingMilestoneId(null)
        setEditingValue('')
    }

    const commitEdit = async (milestoneId: string) => {
        const nextContent = editingValue.trim()
        if (!nextContent) {
            toast.error(t('milestones.emptyError'))
            stopEditing()
            return
        }
        dispatch(
            updateMilestoneContent({ id: milestoneId, content: nextContent })
        )
        const nextMilestones = milestones.map((m) =>
            m.id === milestoneId ? { ...m, content: nextContent } : m
        )
        await persistPlan(nextMilestones)
        stopEditing()
    }

    const getNextMilestoneId = () => {
        const numericIds = milestones
            .map((m) => Number.parseInt(m.id, 10))
            .filter((n) => Number.isFinite(n))
        if (numericIds.length === milestones.length) {
            return String(Math.max(0, ...numericIds) + 1)
        }
        return `${Date.now()}`
    }

    const handleAddMilestone = async () => {
        const newMilestone: Milestone = {
            id: getNextMilestoneId(),
            content: t('milestones.newMilestone'),
            status: 'pending'
        }
        dispatch(addMilestone(newMilestone))
        await persistPlan([...milestones, newMilestone])
        setIsOpen(true)
        startEditing(newMilestone)
    }

    const handleDeleteMilestone = async (milestoneId: string) => {
        const nextMilestones = milestones.filter((m) => m.id !== milestoneId)
        dispatch(deleteMilestone({ id: milestoneId }))
        await persistPlan(nextMilestones)
    }

    const handleBuildClick = () => {
        // Clear plan modification suggestions when starting build
        dispatch(clearPlanModificationOptions())
        if (selectedMilestone && onBuildMilestone && planSummary) {
            // Call the callback to trigger building the milestone
            onBuildMilestone(selectedMilestone, {
                summary: planSummary,
                milestones
            })
        }
        dispatch(setBuildMode(BUILD_MODE.BUILD))
    }

    const handleBuildAllClick = () => {
        // Clear plan modification suggestions when starting build
        dispatch(clearPlanModificationOptions())
        if (onBuildAllMilestones && planSummary) {
            // Call the callback to trigger building all milestones
            onBuildAllMilestones({
                summary: planSummary,
                milestones
            })
        }
        dispatch(setBuildMode(BUILD_MODE.BUILD))
    }

    const handleModifyPlan = () => {
        // Clear any existing plan modification suggestions
        dispatch(clearPlanModificationOptions())
        // Collapse the milestone list instead of clearing it
        // The plan data stays intact until new plan data arrives
        setIsOpen(false)
        onModifyPlan?.()
    }

    const handleMilestoneClick = (milestone: Milestone) => {
        if (milestone.status === 'pending') {
            dispatch(setSelectedMilestoneId(milestone.id))
        }
    }

    useEffect(() => {
        if (buildMode === BUILD_MODE.DESIGN || buildMode === BUILD_MODE.HELP) {
            setIsOpen(false)
        }
    }, [buildMode])

    // Scroll to keep suggestion box visible when milestone list is expanded
    useEffect(() => {
        if (isOpen && containerRef.current) {
            // Small delay to let the collapsible animation start
            setTimeout(() => {
                containerRef.current?.scrollIntoView({
                    behavior: 'smooth',
                    block: 'end'
                })
            }, 100)
        }
    }, [isOpen])

    if (milestones.length === 0) {
        return null
    }

    return (
        <div
            ref={containerRef}
            className={cn(
                'rounded-xl px-3 pt-3 pb-6 !-mb-4 border border-white/30 backdrop-blur-sm overflow-hidden relative',
                BUILD_MODE_STYLES[buildMode],
                className
            )}
        >
            {/* Decorative overlay */}
            <div className="absolute inset-0 bg-white/10 pointer-events-none" />
            <div className="absolute top-0 left-0 right-0 h-px bg-white/50" />

            <Collapsible open={isOpen} onOpenChange={setIsOpen}>
                {(buildMode === BUILD_MODE.BUILD ||
                    buildMode === BUILD_MODE.PLAN) && (
                    <div className="flex items-center justify-between">
                        <CollapsibleTrigger className="flex items-center gap-1.5 text-charcoal hover:opacity-80 transition-opacity">
                            <span className="text-xs font-medium">
                                {isOpen
                                    ? t('milestones.collapse')
                                    : t('milestones.viewAll')}
                            </span>
                            <ChevronDown
                                className={cn(
                                    'size-3.5 transition-transform duration-200',
                                    isOpen && 'rotate-180'
                                )}
                            />
                        </CollapsibleTrigger>
                        {buildMode === BUILD_MODE.BUILD && (
                            <div className="flex items-center gap-x-[6px]">
                                <span className="text-xs text-charcoal">
                                    {progress}%
                                </span>
                                {isLoading && (
                                    <Icon
                                        name="loader"
                                        className="size-4 text-black animate-spin"
                                    />
                                )}
                            </div>
                        )}
                        {buildMode === BUILD_MODE.PLAN && !isOpen && (
                            <Button
                                className={cn(
                                    'bg-charcoal text-white rounded-lg h-7 px-4 gap-1.5 text-xs font-medium shrink-0 shadow-lg shadow-charcoal/20 transition-all duration-200',
                                    isLoading
                                        ? 'opacity-50 cursor-not-allowed'
                                        : 'hover:shadow-xl hover:shadow-charcoal/30 hover:-translate-y-0.5 active:scale-95'
                                )}
                                onClick={handleModifyPlan}
                                disabled={isLoading}
                            >
                                <Icon
                                    name="document-check"
                                    className="size-3.5 fill-white"
                                />
                                {t('milestones.modifyPlan')}
                            </Button>
                        )}
                    </div>
                )}

                {/* Collapsible milestone list */}
                <CollapsibleContent>
                    <div className="space-y-2 mt-3">
                        {milestones.map((milestone) => {
                            const isSelected =
                                selectedMilestone?.id === milestone.id
                            const isPending = milestone.status === 'pending'
                            const isEditing =
                                editingMilestoneId === milestone.id

                            return (
                                <div
                                    key={milestone.id}
                                    className={cn(
                                        'group flex items-center gap-2 p-1.5 -mx-1.5 rounded-lg transition-all duration-200',
                                        isPending &&
                                            'cursor-pointer hover:bg-white/20 hover:shadow-sm'
                                    )}
                                    onClick={() =>
                                        !isEditing &&
                                        handleMilestoneClick(milestone)
                                    }
                                >
                                    {/* Status icon */}
                                    {milestone.status === 'completed' && (
                                        <Check className="size-4 text-black shrink-0" />
                                    )}
                                    {isSelected && (
                                        <div className="relative">
                                            <div className="size-4 shrink-0 flex items-center justify-center">
                                                <div className="size-2.5 rounded-full bg-black" />
                                            </div>
                                            <Circle className="size-4 text-black shrink-0 absolute top-0" />
                                        </div>
                                    )}
                                    {isPending && !isSelected && (
                                        <Circle className="size-4 text-black shrink-0" />
                                    )}

                                    {/* Content */}
                                    {isEditing ? (
                                        <input
                                            className={cn(
                                                'flex-1 min-w-0 bg-white/60 text-black text-xs rounded-md px-2 py-1 outline-none',
                                                'border border-black/15 focus:border-black/30'
                                            )}
                                            autoFocus
                                            value={editingValue}
                                            onChange={(e) =>
                                                setEditingValue(e.target.value)
                                            }
                                            onClick={(e) => e.stopPropagation()}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') {
                                                    e.preventDefault()
                                                    ;(
                                                        e.currentTarget as HTMLInputElement
                                                    ).blur()
                                                } else if (e.key === 'Escape') {
                                                    e.preventDefault()
                                                    stopEditing()
                                                }
                                            }}
                                            onBlur={() =>
                                                commitEdit(milestone.id)
                                            }
                                        />
                                    ) : (
                                        <span
                                            className={cn(
                                                'text-xs text-black flex-1 min-w-0',
                                                milestone.status ===
                                                    'completed' &&
                                                    'line-through opacity-60',
                                                isSelected && 'font-medium'
                                            )}
                                        >
                                            {milestone.content}
                                        </span>
                                    )}

                                    {/* Inline edit/delete controls */}
                                    {canEditMilestones &&
                                        isPending &&
                                        !isEditing && (
                                            <div
                                                className={cn(
                                                    'flex items-center gap-1 shrink-0',
                                                    'opacity-0 group-hover:opacity-100 transition-opacity'
                                                )}
                                                onClick={(e) =>
                                                    e.stopPropagation()
                                                }
                                            >
                                                <button
                                                    type="button"
                                                    className="p-1 rounded-md hover:bg-white/30"
                                                    aria-label={t(
                                                        'milestones.aria.edit'
                                                    )}
                                                    onClick={() =>
                                                        startEditing(milestone)
                                                    }
                                                >
                                                    <Pencil className="size-3.5 text-black" />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="p-1 rounded-md hover:bg-white/30"
                                                    aria-label={t(
                                                        'milestones.aria.delete'
                                                    )}
                                                    onClick={() =>
                                                        handleDeleteMilestone(
                                                            milestone.id
                                                        )
                                                    }
                                                >
                                                    <Trash2 className="size-3.5 text-black" />
                                                </button>
                                            </div>
                                        )}
                                </div>
                            )
                        })}
                        {buildMode === BUILD_MODE.PLAN && (
                            <div className="flex items-center gap-2 mt-2">
                                <Button
                                    className={cn(
                                        'bg-charcoal text-white rounded-lg h-7 px-4 gap-1.5 text-xs font-medium shrink-0 shadow-lg shadow-charcoal/20 transition-all duration-200',
                                        isLoading
                                            ? 'opacity-50 cursor-not-allowed'
                                            : 'hover:shadow-xl hover:shadow-charcoal/30 hover:-translate-y-0.5 active:scale-95'
                                    )}
                                    onClick={handleAddMilestone}
                                    disabled={isLoading}
                                >
                                    <Plus className="size-3.5 text-white" />
                                    {t('milestones.addMilestone')}
                                </Button>
                                <Button
                                    className={cn(
                                        'bg-charcoal text-white rounded-lg h-7 px-4 gap-1.5 text-xs font-medium shrink-0 shadow-lg shadow-charcoal/20 transition-all duration-200',
                                        isLoading
                                            ? 'opacity-50 cursor-not-allowed'
                                            : 'hover:shadow-xl hover:shadow-charcoal/30 hover:-translate-y-0.5 active:scale-95'
                                    )}
                                    onClick={handleModifyPlan}
                                    disabled={isLoading}
                                >
                                    <Icon
                                        name="document-check"
                                        className="size-3.5 fill-white"
                                    />
                                    {t('milestones.modifyPlan')}
                                </Button>
                            </div>
                        )}
                    </div>
                </CollapsibleContent>
            </Collapsible>

            {buildMode === BUILD_MODE.HELP && (
                <p className="text-white font-semibold text-xs mb-3">
                    {t('milestones.helpMode')}
                </p>
            )}

            {buildMode === BUILD_MODE.DESIGN && (
                <p className="text-white font-semibold text-xs mb-3">
                    {t('milestones.designMode')}
                </p>
            )}

            {/* Divider */}
            <div className="my-3 h-px bg-black/20" />

            {/* Next milestone section - always visible */}
            <div className="flex justify-between gap-x-4 items-start p-2 -mx-0.5 rounded-lg bg-white/15 backdrop-blur-sm">
                <div className="flex flex-col">
                    <span
                        className={clsx(
                            'text-[10px] font-semibold uppercase tracking-wide',
                            {
                                'text-green-4': buildMode === BUILD_MODE.HELP,
                                'text-green-3': buildMode === BUILD_MODE.BUILD,
                                'text-orange-2':
                                    buildMode === BUILD_MODE.DESIGN,
                                'text-black/70': buildMode !== BUILD_MODE.HELP
                            }
                        )}
                    >
                        {selectedMilestone
                            ? t('milestones.nextMilestone')
                            : t('milestones.status')}
                    </span>
                    {selectedMilestone ? (
                        <p className="font-semibold text-black mt-1 text-xs leading-snug">
                            {selectedMilestone.content}
                        </p>
                    ) : (
                        <p className="font-semibold text-black mt-1 text-xs leading-snug">
                            {t('milestones.allCompleted')}
                        </p>
                    )}
                </div>
                {selectedMilestone && (
                    <div className="flex flex-col md:flex-row gap-2">
                        <Button
                            className={cn(
                                'bg-violet text-white rounded-lg h-7 px-4 gap-1.5 text-xs font-medium shrink-0 shadow-lg shadow-violet/30 transition-all duration-200',
                                isLoading
                                    ? 'opacity-50 cursor-not-allowed'
                                    : 'hover:shadow-xl hover:shadow-violet/40 hover:-translate-y-0.5 active:scale-95'
                            )}
                            onClick={handleBuildClick}
                            disabled={isLoading}
                        >
                            <Icon
                                name="build-2"
                                className="size-3.5 fill-white"
                            />
                            {t('milestones.build')}
                        </Button>
                        <Button
                            className={cn(
                                'bg-sky-blue text-charcoal rounded-lg h-7 px-4 gap-1.5 text-xs font-medium shrink-0 shadow-lg shadow-sky-blue/30 transition-all duration-200',
                                isLoading
                                    ? 'opacity-50 cursor-not-allowed'
                                    : 'hover:shadow-xl hover:shadow-sky-blue/40 hover:-translate-y-0.5 active:scale-95'
                            )}
                            onClick={handleBuildAllClick}
                            disabled={isLoading}
                        >
                            <Icon
                                name="build-2"
                                className="size-3.5 fill-charcoal"
                            />
                            {t('milestones.buildAll')}
                        </Button>
                    </div>
                )}
            </div>
        </div>
    )
}

export default MilestoneTracker
