import type { ISession } from '@/typings/agent'

type SessionMetadata = NonNullable<ISession['metadata']>

type BackendSession = Omit<ISession, 'metadata' | 'llm_setting_id'> & {
    metadata?: SessionMetadata
    llm_setting_id?: string | null
    session_metadata?: SessionMetadata
    model_setting_id?: string | null
}

export function normalizeSession(session: BackendSession): ISession {
    const {
        metadata,
        llm_setting_id,
        session_metadata,
        model_setting_id,
        ...rest
    } = session

    return {
        ...rest,
        llm_setting_id: llm_setting_id ?? model_setting_id,
        metadata: metadata ?? session_metadata
    }
}

export function normalizeSessions(sessions: BackendSession[]): ISession[] {
    return sessions.map(normalizeSession)
}
