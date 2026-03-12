import type { DesignChange } from './types'

type SocketCommandSender = (payload: {
    type: string
    content: Record<string, unknown>
}) => boolean

export interface DesignStateSocketResponse {
    operation?: string
    success?: boolean
    error?: string
    request_id?: string
    session_id?: string
    changes?: DesignChange[]
    redo_changes?: DesignChange[]
    updated_at?: number
}

const RESPONSE_EVENT = 'design-mode-state-response'
const SYNC_RESPONSE_EVENT = 'design-mode-sync-response'

function buildRequestId() {
    if (
        typeof crypto !== 'undefined' &&
        typeof crypto.randomUUID === 'function'
    ) {
        return crypto.randomUUID()
    }

    return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function requestDesignState(
    sendSocketMessage: SocketCommandSender,
    {
        type,
        operation,
        content,
        timeoutMs = 15_000
    }: {
        type: 'design_get_state' | 'design_save_state'
        operation: 'design_state_loaded' | 'design_state_saved'
        content: Record<string, unknown>
        timeoutMs?: number
    }
) {
    return await new Promise<DesignStateSocketResponse>((resolve, reject) => {
        const requestId = buildRequestId()

        const cleanup = (timeoutId: ReturnType<typeof setTimeout>) => {
            clearTimeout(timeoutId)
            window.removeEventListener(
                RESPONSE_EVENT,
                handleResponse as EventListener
            )
        }

        const handleResponse = (event: Event) => {
            const detail = (event as CustomEvent<DesignStateSocketResponse>).detail
            if (!detail || detail.operation !== operation) return
            if (detail.request_id !== requestId) return

            cleanup(timeoutId)

            if (detail.success === false) {
                reject(
                    new Error(
                        typeof detail.error === 'string'
                            ? detail.error
                            : `Socket command ${type} failed`
                    )
                )
                return
            }

            resolve(detail)
        }

        const timeoutId = setTimeout(() => {
            cleanup(timeoutId)
            reject(new Error(`Socket command ${type} timed out`))
        }, timeoutMs)

        window.addEventListener(
            RESPONSE_EVENT,
            handleResponse as EventListener
        )

        const sent = sendSocketMessage({
            type,
            content: {
                ...content,
                request_id: requestId
            }
        })

        if (!sent) {
            cleanup(timeoutId)
            reject(new Error('Socket connection is not open'))
        }
    })
}

export interface DesignSyncSocketResponse {
    operation?: string
    success?: boolean
    applied?: number
    total?: number
    remaining?: number
    errors?: string[]
    summary?: string
    remaining_changes?: DesignChange[]
    event_id?: string
    error_type?: string
    message?: string
    session_id?: string
}

async function requestDesignSync(
    sendSocketMessage: SocketCommandSender,
    {
        type,
        operation,
        content,
        sessionId,
        timeoutMs = 120_000,
        timeoutMessage
    }: {
        type: 'design_sync_state' | 'slide_deck_sync_state'
        operation:
            | 'design_sync_state_complete'
            | 'slide_deck_sync_state_complete'
        content: Record<string, unknown>
        sessionId: string
        timeoutMs?: number
        timeoutMessage: string
    }
) {
    return await new Promise<DesignSyncSocketResponse>((resolve, reject) => {
        const cleanup = (timeoutId: ReturnType<typeof setTimeout>) => {
            clearTimeout(timeoutId)
            window.removeEventListener(
                SYNC_RESPONSE_EVENT,
                handleResponse as EventListener
            )
        }

        const handleResponse = (event: Event) => {
            const detail = (event as CustomEvent<DesignSyncSocketResponse>).detail
            if (!detail || detail.operation !== operation) return
            if (
                typeof detail.session_id === 'string' &&
                detail.session_id &&
                detail.session_id !== sessionId
            ) {
                return
            }

            cleanup(timeoutId)

            if (typeof detail.error_type === 'string') {
                reject(
                    new Error(
                        typeof detail.message === 'string'
                            ? detail.message
                            : `Socket command ${type} failed`
                    )
                )
                return
            }

            resolve(detail)
        }

        const timeoutId = setTimeout(() => {
            cleanup(timeoutId)
            reject(new Error(timeoutMessage))
        }, timeoutMs)

        window.addEventListener(
            SYNC_RESPONSE_EVENT,
            handleResponse as EventListener
        )

        const sent = sendSocketMessage({
            type,
            content
        })

        if (!sent) {
            cleanup(timeoutId)
            reject(new Error('Socket connection is not open'))
        }
    })
}

export async function loadDesignStateViaSocket(
    sendSocketMessage: SocketCommandSender,
    sessionId: string
) {
    return await requestDesignState(sendSocketMessage, {
        type: 'design_get_state',
        operation: 'design_state_loaded',
        content: { session_id: sessionId }
    })
}

export async function saveDesignStateViaSocket(
    sendSocketMessage: SocketCommandSender,
    {
        sessionId,
        changes,
        redoChanges
    }: {
        sessionId: string
        changes: DesignChange[]
        redoChanges: DesignChange[]
    }
) {
    return await requestDesignState(sendSocketMessage, {
        type: 'design_save_state',
        operation: 'design_state_saved',
        content: {
            session_id: sessionId,
            changes,
            redo_changes: redoChanges
        }
    })
}

export async function syncDesignStateViaSocket(
    sendSocketMessage: SocketCommandSender,
    sessionId: string
) {
    return await requestDesignSync(sendSocketMessage, {
        type: 'design_sync_state',
        operation: 'design_sync_state_complete',
        content: { session_id: sessionId },
        sessionId,
        timeoutMessage: 'Design sync timed out'
    })
}

export async function syncSlideDeckStateViaSocket(
    sendSocketMessage: SocketCommandSender,
    {
        sessionId,
        presentationName
    }: {
        sessionId: string
        presentationName: string
    }
) {
    return await requestDesignSync(sendSocketMessage, {
        type: 'slide_deck_sync_state',
        operation: 'slide_deck_sync_state_complete',
        content: {
            session_id: sessionId,
            presentation_name: presentationName
        },
        sessionId,
        timeoutMessage: 'Slide deck sync timed out'
    })
}
