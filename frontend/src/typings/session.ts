import { ISession, IEvent } from './agent'

export interface SessionsResponse {
    sessions: ISession[]
}

export interface SessionEventsResponse {
    events: IEvent[]
    run_status?: string | null
}

export interface CreateSessionRequest {
    deviceId: string
    name?: string
}

export interface UpdateSessionRequest {
    name?: string
    status?: string
}

export interface SessionFile {
    id: string
    name: string
    content_type?: string
    url: string
    size: number
}

export interface SessionFilesResponse {
    files: SessionFile[]
}

// Fork session types
export type ForkType = 'research_to_website' | 'research_to_slide'

export type SandboxMode = 'share' | 'new'

export interface ForkContext {
    attachments: string[]
    additional_instruction?: string | null
}

export interface ForkSessionRequest {
    fork_type: ForkType
    sandbox_mode: SandboxMode
    context: ForkContext
    model_setting_id?: string | null
}

export interface ForkSessionResponse {
    session_id: string
    parent_session_id: string
    name: string
    agent_type: string
    sandbox_id?: string | null
    sandbox_mode: SandboxMode
    model_setting_id?: string | null
}
