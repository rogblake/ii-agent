import { useTranslation } from 'react-i18next'

import type { SyncProgress } from './types'

export function SavingOverlay({
    isSaving,
    syncProgress,
    zIndex = 9999
}: {
    isSaving: boolean
    syncProgress: SyncProgress | null
    zIndex?: number
}) {
    const { t } = useTranslation()

    if (!isSaving) return null

    const percent =
        syncProgress && syncProgress.total > 0
            ? Math.round((syncProgress.processed / syncProgress.total) * 100)
            : 0

    return (
        <div
            className="fixed inset-0 flex items-center justify-center bg-black/50 p-4"
            style={{ zIndex }}
        >
            <div className="flex w-96 max-w-md flex-col items-center gap-4 rounded-xl border border-sky-blue bg-white p-6 shadow-xl dark:bg-charcoal">
                <div className="h-12 w-12 animate-spin rounded-full border-4 border-sky-blue border-t-black dark:border-t-black" />
                <p className="font-medium text-black dark:text-white">
                    {t('designMode.preview.syncingToSandbox')}
                </p>

                <div className="w-full space-y-3">
                    <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
                        <span>
                            {syncProgress &&
                            syncProgress.total > 0 &&
                            syncProgress.current &&
                            syncProgress.current > 0
                                ? t('designMode.preview.changeOfTotal', {
                                      current: syncProgress.current,
                                      total: syncProgress.total
                                  })
                                : t('designMode.preview.starting')}
                        </span>
                        <span>{percent}%</span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700">
                        <div
                            className="h-2 rounded-full bg-sky-blue transition-all duration-300"
                            style={{
                                width: `${percent}%`
                            }}
                        />
                    </div>
                    {syncProgress &&
                        syncProgress.applied !== undefined &&
                        syncProgress.errors !== undefined &&
                        syncProgress.processed > 0 && (
                            <p className="break-words text-center text-xs leading-relaxed text-gray-500 dark:text-gray-400">
                                {t('designMode.preview.syncStats', {
                                    applied: syncProgress.applied,
                                    errors: syncProgress.errors
                                })}
                            </p>
                        )}
                </div>
            </div>
        </div>
    )
}
