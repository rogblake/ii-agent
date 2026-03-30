import { useEffect, useRef } from 'react'
import { useParams } from 'react-router'
import { useAppDispatch, store } from '@/state'
import { selectSessionState } from '@/state/slice/session-state'
import {
    setBuildMode,
    setSelectedFeature,
    setMilestones,
    setSelectedMilestoneId,
    setPlanSummary,
    setPlanModificationOptions,
    setBuildStep,
    setSelectedBuildStep,
    setRunStatus,
    setCouncilPreference,
    resetCouncilMode,
    resetFileExplorer
} from '@/state'
import { BUILD_MODE, BUILD_STEP } from '@/typings/agent'

/**
 * Hook to restore session state when entering a session
 */
export function useSessionEnter() {
    const { sessionId } = useParams()
    const dispatch = useAppDispatch()
    const previousSessionIdRef = useRef<string | undefined>(undefined)

    useEffect(() => {
        const currentSessionId = sessionId
        const previousSessionId = previousSessionIdRef.current

        // Check if we're entering a new session (sessionId changed from undefined/different to a value)
        const isEnteringSession =
            currentSessionId && currentSessionId !== previousSessionId

        if (isEnteringSession) {
            // Reset file explorer state for new session
            dispatch(resetFileExplorer())

            // Try to restore cached session state
            const state = store.getState()
            const cachedState = selectSessionState(currentSessionId)(state)

            if (cachedState) {
                // Restore all persistent state including buildStep, isWaitingForInput, and isStopped
                // These should persist so returning to a session shows the correct state
                const isFreshEntry = previousSessionId === undefined
                dispatch(
                    setBuildMode(
                        isFreshEntry ? BUILD_MODE.BUILD : cachedState.buildMode
                    )
                )

                // Safety check: If buildStep is PLAN but we have no milestones/planSummary,
                // something went wrong (interrupted plan generation). Reset to THINKING.
                const hasPlanData =
                    cachedState.milestones.length > 0 ||
                    cachedState.planSummary !== null
                const safeBuildStep =
                    cachedState.buildStep === BUILD_STEP.PLAN && !hasPlanData
                        ? BUILD_STEP.THINKING
                        : cachedState.buildStep

                dispatch(setBuildStep(safeBuildStep))
                dispatch(setSelectedBuildStep(safeBuildStep))
                dispatch(setSelectedFeature(cachedState.selectedFeature))
                dispatch(setMilestones(cachedState.milestones))
                dispatch(
                    setSelectedMilestoneId(cachedState.selectedMilestoneId)
                )
                dispatch(setPlanSummary(cachedState.planSummary))
                dispatch(
                    setPlanModificationOptions(
                        cachedState.planModificationOptions
                    )
                )
                dispatch(setRunStatus(cachedState.runStatus ?? null))

                // Restore council preference
                if (cachedState.councilPreference) {
                    dispatch(
                        setCouncilPreference(cachedState.councilPreference)
                    )
                } else {
                    dispatch(resetCouncilMode())
                }
            } else {
                // No cached state - clear everything to ensure clean slate
                console.log(
                    `No cached state found for session ${currentSessionId}, clearing state for fresh load`
                )
                // Default to Build Mode on fresh loads (reloads/new tabs).
                dispatch(setBuildMode(BUILD_MODE.BUILD))
                dispatch(setRunStatus(null))
                dispatch(setPlanModificationOptions(null))
                dispatch(resetCouncilMode())
            }
        }

        previousSessionIdRef.current = currentSessionId
    }, [sessionId, dispatch])
}
