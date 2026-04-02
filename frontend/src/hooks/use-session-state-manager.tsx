import { useCallback } from 'react'
import { useAppDispatch, useAppSelector } from '@/state'
import {
    saveSessionState,
    clearSessionState,
    type PerSessionState
} from '@/state/slice/session-state'
import {
    setLoading,
    setIsFromNewQuestion,
    setIsCreatingSession,
    setSelectedFeature,
    setBuildMode,
    clearMilestones,
    setPlanModificationOptions,
    selectBuildMode,
    selectSelectedFeature,
    selectMilestones,
    selectSelectedMilestoneId,
    selectPlanSummary,
    selectPlanModificationOptions
} from '@/state'
import {
    setAgentInitialized,
    setBuildStep,
    setSelectedBuildStep,
    setPendingQuery,
    setFullstackProjectInitialized,
    setProjectId,
    setPublished,
    setLatestCheckpoint,
    setRunStatus
} from '@/state'
import {
    selectBuildStep,
    selectRunStatus
} from '@/state/slice/agent'
import { BUILD_MODE, BUILD_STEP, AGENT_TYPE } from '@/typings/agent'

/**
 * Hook to manage per-session state - saving and restoring state when switching sessions
 */
export function useSessionStateManager() {
    const dispatch = useAppDispatch()

    // Get current state values
    // Note: isCompleted/isStopped/isWaitingForInput are derived from runStatus via selectors
    const buildMode = useAppSelector(selectBuildMode)
    const buildStep = useAppSelector(selectBuildStep)
    const selectedFeature = useAppSelector(selectSelectedFeature)
    const milestones = useAppSelector(selectMilestones)
    const selectedMilestoneId = useAppSelector(selectSelectedMilestoneId)
    const planSummary = useAppSelector(selectPlanSummary)
    const planModificationOptions = useAppSelector(
        selectPlanModificationOptions
    )
    const runStatus = useAppSelector(selectRunStatus)

    /**
     * Save current session state to cache
     * Note: isCompleted/isStopped/isWaitingForInput are derived from runStatus via selectors.
     * We don't save isLoading as it's truly transient.
     */
    const saveCurrentSessionState = useCallback(
        (sessionId: string) => {
            const state: PerSessionState = {
                buildMode,
                buildStep,
                selectedFeature,
                milestones,
                selectedMilestoneId,
                planSummary,
                planModificationOptions,
                runStatus
            }
            dispatch(saveSessionState({ sessionId, state }))
        },
        [
            dispatch,
            buildMode,
            buildStep,
            selectedFeature,
            milestones,
            selectedMilestoneId,
            planSummary,
            planModificationOptions,
            runStatus
        ]
    )

    /**
     * Reset all session-related state to defaults
     * This should be called when leaving a session or going to home
     */
    const resetSessionState = useCallback(() => {
        // Reset UI state
        dispatch(setLoading(false))
        dispatch(setIsFromNewQuestion(false))
        dispatch(setIsCreatingSession(false))
        dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        dispatch(setBuildMode(BUILD_MODE.BUILD))
        dispatch(clearMilestones())
        dispatch(setPlanModificationOptions(null))

        // Reset agent state — isCompleted/isStopped/isWaitingForInput derived from runStatus
        dispatch(setRunStatus(null))
        dispatch(setAgentInitialized(false))
        dispatch(setBuildStep(BUILD_STEP.THINKING))
        dispatch(setSelectedBuildStep(BUILD_STEP.THINKING))
        dispatch(setPendingQuery(null))
        dispatch(setFullstackProjectInitialized(false))
        dispatch(setProjectId(null))
        dispatch(setPublished(null))
        dispatch(setLatestCheckpoint(null))
    }, [dispatch])

    /**
     * Clear cached session state
     */
    const clearCachedSessionState = useCallback(
        (sessionId: string) => {
            dispatch(clearSessionState(sessionId))
        },
        [dispatch]
    )

    return {
        saveCurrentSessionState,
        resetSessionState,
        clearCachedSessionState
    }
}
