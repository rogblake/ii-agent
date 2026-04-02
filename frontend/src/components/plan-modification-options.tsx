import { Sparkles } from 'lucide-react'

import { cn } from '@/lib/utils'
import {
    clearPlanModificationOptions,
    selectIsLoading,
    selectPlanModificationOptions,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { PlanModificationSuggestion } from '@/typings/agent'
import { useTranslation } from 'react-i18next'

interface PlanModificationOptionsProps {
    className?: string
    onSubmit?: (text: string) => void
}

const PlanModificationOptions = ({
    className,
    onSubmit
}: PlanModificationOptionsProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const options = useAppSelector(selectPlanModificationOptions)
    const isLoading = useAppSelector(selectIsLoading)
    const defaultMessage = t('plan.modification.title')

    if (!options || !Array.isArray(options.suggestions)) {
        return null
    }

    const handleOptionClick = (suggestion: PlanModificationSuggestion) => {
        // Clear the options
        dispatch(clearPlanModificationOptions())
        // Submit the modification request
        onSubmit?.(suggestion.prompt_template)
    }

    return (
        <div
            className={cn(
                'rounded-xl overflow-hidden',
                'bg-mist/30',
                'dark:bg-mist/15',
                'border border-mist/50 dark:border-mist/30',
                'shadow-md',
                className
            )}
        >
            {/* Header */}
            <div className="px-4 py-3">
                <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-mist/50 dark:bg-mist/30">
                        <Sparkles className="size-4 text-charcoal dark:text-mist" />
                    </div>
                    <h3 className="text-sm font-semibold text-charcoal dark:text-white">
                        {t('plan.modification.title')}
                    </h3>
                </div>
                {options.message &&
                    options.message !== defaultMessage && (
                    <p className="mt-2 text-xs text-charcoal/70 dark:text-white/70 ml-9">
                        {options.message}
                    </p>
                )}
            </div>

            {/* Suggestions */}
            <div className="px-4 pb-4">
                <div className="flex flex-wrap gap-2">
                    {options.suggestions.map((suggestion) => (
                        <button
                            key={suggestion.id}
                            onClick={() => handleOptionClick(suggestion)}
                            disabled={isLoading}
                            className={cn(
                                'px-4 py-2 rounded-lg text-sm text-left transition-all duration-200',
                                'bg-white/90 dark:bg-charcoal/70',
                                'hover:bg-white dark:hover:bg-charcoal',
                                'border border-mist/50 dark:border-mist/40',
                                'hover:border-mist dark:hover:border-mist',
                                'text-charcoal dark:text-white',
                                'hover:shadow-lg hover:-translate-y-0.5',
                                'font-medium',
                                'active:scale-95',
                                isLoading &&
                                    'opacity-50 cursor-not-allowed hover:shadow-none hover:translate-y-0'
                            )}
                            title={suggestion.description}
                        >
                            {suggestion.label}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default PlanModificationOptions
