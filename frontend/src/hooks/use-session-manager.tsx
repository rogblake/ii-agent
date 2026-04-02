import { sessionService } from '@/services/session.service'
import {
    selectIsFromNewQuestion,
    setAgentInitialized,
    setIsFromNewQuestion,
    setRunStatus,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { setLoading } from '@/state/slice/ui'
import {
    AgentEvent,
    IEvent,
    isActiveRunStatus
} from '@/typings/agent'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router'

export function useSessionManager({
    handleEvent
}: {
    handleEvent: (
        data: {
            id: string
            name: AgentEvent
            content: Record<string, unknown>
            run_id?: string
            session_id?: string
        },
        ignoreClickAction?: boolean
    ) => void
}) {
    const dispatch = useAppDispatch()
    const params = useParams()
    const location = useLocation()
    const isFromNewQuestion = useAppSelector(selectIsFromNewQuestion)
    const [sessionId, setSessionId] = useState<string | null>(null)
    const [isLoadingSession, setIsLoadingSession] = useState(false)
    const [isReplayMode, setIsReplayMode] = useState(
        location.pathname.includes('/share/')
    )
    const eventsDataRef = useRef<{
        events: IEvent[]
    } | null>(null)
    const delayTimeRef = useRef<number>(1000)
    const fetchingRef = useRef<boolean>(false)
    const processedSessionRef = useRef<string | null>(null)

    // Get session ID from URL params and determine replay mode
    useEffect(() => {
        const id = params.sessionId || null
        setSessionId(id)
        dispatch(setAgentInitialized(false))

        // Reset processed session when session ID changes
        if (processedSessionRef.current !== id) {
            processedSessionRef.current = null
        }

        // // If navigated from new question submission, it's not replay mode
        // if (isFromNewQuestion) {
        //     setIsReplayMode(false)
        // } else if (id) {
        //     // Otherwise, if there's a session ID in the URL, it's replay mode
        //     setIsReplayMode(true)
        // } else {
        //     setIsReplayMode(false)
        // }
    }, [params.sessionId, isFromNewQuestion, dispatch])

    const processAllEventsImmediately = () => {
        delayTimeRef.current = 0
        setIsReplayMode(false)
    }

    const fetchSessionEvents = useCallback(async () => {
        const id = params.sessionId
        if (!id || fetchingRef.current || processedSessionRef.current === id)
            return

        fetchingRef.current = true
        processedSessionRef.current = id
        setIsLoadingSession(true)
        try {
            const data = isReplayMode
                ? await sessionService.getPublicSessionEvents(id)
                : await sessionService.getSessionEvents(id)

            if (data.events && Array.isArray(data.events)) {
                // Store events data for potential immediate processing
                eventsDataRef.current = { events: data.events }

                // Function to process events with delay
                const processEventsWithDelay = async () => {
                    for (let i = 0; i < data.events.length; i++) {
                        const event = data.events[i]

                        const ignoreEvents = [
                            AgentEvent.AGENT_INITIALIZED,
                            AgentEvent.WORKSPACE_INFO,
                            AgentEvent.CONNECTION_ESTABLISHED,
                            AgentEvent.STATUS_UPDATE,
                            AgentEvent.SANDBOX_STATUS,
                            AgentEvent.PROCESSING,
                            AgentEvent.AGENT_CONTINUE
                        ].includes(event.name)
                        const isDelay =
                            delayTimeRef.current > 0 &&
                            i > 0 &&
                            isReplayMode &&
                            !ignoreEvents
                        if (isDelay) {
                            dispatch(setLoading(true))
                            await new Promise((resolve) =>
                                setTimeout(resolve, delayTimeRef.current)
                            )
                        }
                        // For events that manage agent state, we need to process them regardless of delay
                        // to ensure proper UI state reconstruction during replay
                        const isAgentStateEvent = [
                            AgentEvent.SUB_AGENT_COMPLETE,
                            AgentEvent.AGENT_RESPONSE,
                            AgentEvent.TOOL_CALL,
                            AgentEvent.TOOL_RESULT,
                            AgentEvent.PLAN_GENERATED,
                            AgentEvent.MILESTONE_UPDATE,
                            AgentEvent.PLAN_MODIFICATION_OPTIONS
                        ].includes(event.name)

                        handleEvent(
                            {
                                id: event.id,
                                name: event.name,
                                // Inject session_id into content for replay (mirrors SocketIOSubscriber behavior)
                                content: { ...event.content, session_id: id },
                                // Include run_id and session_id at top level for HITL continue_run
                                run_id: event.run_id,
                                session_id: event.session_id ?? id
                            },
                            !isDelay && !isAgentStateEvent // Don't ignore agent state events
                        )
                    }

                    // After replaying all events, reconcile final state from run_status
                    // This is the authoritative source from BE — it prevents desync
                    // isCompleted/isStopped/isWaitingForInput are derived from runStatus via selectors
                    const runStatus = data.run_status as string | undefined
                    if (runStatus) {
                        dispatch(setRunStatus(runStatus))
                        dispatch(setLoading(isActiveRunStatus(runStatus)))
                    } else {
                        // No run task yet — ensure clean state
                        dispatch(setRunStatus(null))
                        dispatch(setLoading(false))
                    }

                    setIsReplayMode(false)
                }

                // Await so the finally block runs after all events are processed
                await processEventsWithDelay()
            }
        } catch (error) {
            console.error('Failed to fetch session events:', error)
        } finally {
            setIsLoadingSession(false)
            fetchingRef.current = false
        }
    }, [params.sessionId, handleEvent, dispatch, isReplayMode])

    useEffect(() => {
        fetchSessionEvents()
    }, [fetchSessionEvents])

    const setSessionIdWithSource = useCallback(
        (id: string, fromNewQuestion = false) => {
            if (fromNewQuestion) {
                dispatch(setIsFromNewQuestion(true))
            }
            setSessionId(id)
        },
        [dispatch]
    )

    return {
        sessionId,
        isLoadingSession,
        isReplayMode,
        setSessionId: setSessionIdWithSource,
        fetchSessionEvents,
        processAllEventsImmediately
    }
}
