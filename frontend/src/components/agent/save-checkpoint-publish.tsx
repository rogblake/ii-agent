'use client'

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { PublishButton } from '@/components/agent/publish-button'

interface SaveCheckpointPublishProps {
    result: unknown
    isResult: boolean
}

type SaveCheckpointResult = {
    project_directory?: string
    revision?: string
    [key: string]: unknown
}

const isPlainObject = (value: unknown): value is Record<string, unknown> => {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export const SaveCheckpointPublish = ({
    result,
    isResult
}: SaveCheckpointPublishProps) => {
    const { t } = useTranslation()
    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    const checkpointResult: SaveCheckpointResult | null = useMemo(() => {
        if (!isPlainObject(result)) return null
        return result as SaveCheckpointResult
    }, [result])

    const projectDirectory = checkpointResult?.project_directory
    const revision = checkpointResult?.revision

    if (
        !isResult ||
        isShareMode ||
        !projectDirectory ||
        !revision ||
        typeof projectDirectory !== 'string' ||
        typeof revision !== 'string'
    ) {
        return null
    }

    return (
        <div className="mt-3 space-y-2 bg-firefly/[0.18] dark:bg-sky-blue/[0.18] border border-grey rounded-xl p-4">
            <div className="text-sm font-medium">
                {t('agent.checkpoint.ready')}
            </div>
            <div className="text-xs">
                <span className="font-semibold">
                    {t('agent.checkpoint.projectLabel')}:
                </span>{' '}
                <span className="break-all">{projectDirectory}</span>
            </div>
            <div className="text-xs">
                <span className="font-semibold">
                    {t('agent.checkpoint.revisionLabel')}:
                </span>{' '}
                <code className="rounded break-all bg-white/10 px-1 py-0.5 text-xs">
                    {revision}
                </code>
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
                <PublishButton
                    className="text-xs font-semibold bg-firefly text-sky-blue dark:bg-sky-blue dark:text-black"
                    projectDirectory={projectDirectory}
                    revision={revision}
                />
            </div>
        </div>
    )
}
