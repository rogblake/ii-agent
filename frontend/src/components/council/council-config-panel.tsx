import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    useAppDispatch,
    useAppSelector,
    selectAvailableModels,
    selectCouncilPreference,
    setCouncilPreference,
    resetCouncilMode
} from '@/state'
import type { CouncilPreference } from '@/state/slice/settings'

const MAX_COUNCIL_MODELS = 5

export function CouncilConfigPanel() {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const availableModels = useAppSelector(selectAvailableModels)
    const councilPreference = useAppSelector(selectCouncilPreference)

    const selectedIds = new Set(councilPreference.councilModelIds)

    const handleToggleModel = (modelId: string) => {
        const updated: CouncilPreference = { ...councilPreference }
        if (selectedIds.has(modelId)) {
            updated.councilModelIds = councilPreference.councilModelIds.filter(
                (id) => id !== modelId
            )
        } else {
            if (selectedIds.size >= MAX_COUNCIL_MODELS) return
            updated.councilModelIds = [
                ...councilPreference.councilModelIds,
                modelId
            ]
        }
        dispatch(setCouncilPreference(updated))
    }

    const handleClose = () => {
        dispatch(resetCouncilMode())
    }

    return (
        <div className="w-full rounded-xl border border-grey-3 dark:border-white/10 bg-white dark:bg-charcoal p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-charcoal dark:text-sky-blue">
                    {t(
                        'toolCatalog.chatFeatures.modelCouncil.configTitle',
                        'Select Models for Council'
                    )}
                </h3>
                <Button
                    variant="ghost"
                    size="icon"
                    className="size-6 cursor-pointer text-charcoal dark:text-white hover:bg-grey-3 dark:hover:bg-white/10"
                    onClick={handleClose}
                >
                    <X className="size-4" />
                </Button>
            </div>

            <p className="text-xs text-slate dark:text-white/60 mb-4">
                {t(
                    'toolCatalog.chatFeatures.modelCouncil.configDescription',
                    'Choose 2-5 models to run in parallel. Their responses will be synthesized into a single answer.'
                )}
            </p>

            <div className="flex flex-wrap gap-2 max-h-[280px] overflow-y-auto">
                {availableModels.map((model) => {
                    const isSelected = selectedIds.has(model.id)
                    const isDisabled =
                        !isSelected &&
                        selectedIds.size >= MAX_COUNCIL_MODELS
                    return (
                        <button
                            key={model.id}
                            type="button"
                            disabled={isDisabled}
                            onClick={() => handleToggleModel(model.id)}
                            className={`px-3 py-1.5 text-xs rounded-full border transition-all cursor-pointer
                                ${
                                    isSelected
                                        ? 'bg-sky-blue/15 border-sky-blue text-charcoal dark:text-sky-blue font-medium'
                                        : 'border-grey-3 dark:border-white/15 text-charcoal dark:text-white/80 hover:border-sky-blue/50 hover:bg-sky-blue/5'
                                }
                                ${isDisabled ? 'opacity-40 cursor-not-allowed' : ''}`}
                        >
                            {model.model?.split('@')[0] || model.id}
                        </button>
                    )
                })}
            </div>

            {selectedIds.size < 2 && (
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-3">
                    {t(
                        'toolCatalog.chatFeatures.modelCouncil.minModelsWarning',
                        'Select at least 2 models to use Model Council'
                    )}
                </p>
            )}

            <div className="flex items-center justify-between mt-3 pt-3 border-t border-grey-3 dark:border-white/10">
                <span className="text-xs text-slate dark:text-white/50">
                    {selectedIds.size}/{MAX_COUNCIL_MODELS}{' '}
                    {t('common.selected', 'selected')}
                </span>
            </div>
        </div>
    )
}
