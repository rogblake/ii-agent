import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function ErrorOverlay({
    isEnabled = true,
    error,
    footer
}: {
    isEnabled?: boolean
    error: string | null
    footer?: string
}) {
    const { t } = useTranslation()

    if (!isEnabled || !error) return null

    return (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="max-w-md mx-4 p-6 bg-[#1a1a24] border border-yellow-600/30 rounded-xl shadow-2xl">
                <div className="flex items-start gap-4">
                    <div className="p-2 bg-yellow-600/20 rounded-lg">
                        <AlertTriangle className="h-6 w-6 text-yellow-500" />
                    </div>
                    <div className="flex-1">
                        <h3 className="text-lg font-semibold text-white mb-2">
                            {t('designMode.error.title')}
                        </h3>
                        <p className="text-sm text-gray-400 mb-4">{error}</p>
                        <p className="text-xs text-gray-500">
                            {footer ?? t('designMode.error.hint')}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
