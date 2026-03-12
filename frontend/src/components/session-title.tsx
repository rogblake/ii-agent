import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { ISession } from '@/typings/agent'
import { getSessionDisplayName } from '@/utils/session-title'

interface SessionTitleProps {
    session?: Pick<ISession, 'name' | 'title_pending'> | null
    className?: string
    dotClassName?: string
    fallback?: string
}

const DOT_DELAYS = ['0ms', '160ms', '320ms'] as const

export default function SessionTitle({
    session,
    className,
    dotClassName,
    fallback
}: SessionTitleProps) {
    const { t } = useTranslation()

    if (session?.title_pending) {
        return (
            <span
                role="status"
                aria-label={t('common.loading')}
                className={cn('inline-flex items-center gap-0.5', className)}
            >
                {DOT_DELAYS.map((delay, index) => (
                    <span
                        key={index}
                        aria-hidden="true"
                        className={cn(
                            'session-title-wave-dot size-1 rounded-full bg-current',
                            dotClassName
                        )}
                        style={
                            { animationDelay: delay } as CSSProperties
                        }
                    />
                ))}
                <span className="sr-only">{t('common.loading')}</span>
            </span>
        )
    }

    return (
        <span className={className}>
            {getSessionDisplayName(session, fallback ?? t('common.untitled'))}
        </span>
    )
}
