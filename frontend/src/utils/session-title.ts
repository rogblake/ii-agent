import type { ISession } from '@/typings/agent'

type SessionTitleLike = Pick<ISession, 'name' | 'title_pending'>

export function hasSessionDisplayTitle(
    session?: SessionTitleLike | null
): boolean {
    return Boolean(session?.title_pending || session?.name?.trim())
}

export function getSessionDisplayName(
    session?: SessionTitleLike | null,
    fallback = 'Untitled'
): string {
    const name = session?.name?.trim()
    return name || fallback
}
