export interface SessionPinItem {
    id: string
    session_id: string
    session_name: string | null
    agent_type: string | null
    created_at: string
    session_created_at: string | null
    last_message_at: string | null
}

export interface SessionPinResponse {
    sessions: SessionPinItem[]
    total: number
}

export interface PinActionResponse {
    success: boolean
    message: string
    session_id: string
}
