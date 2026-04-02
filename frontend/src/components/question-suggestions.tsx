import { AGENT_TYPE } from '@/typings'
import { Button } from './ui/button'
import { useTranslation } from 'react-i18next'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

interface SuggestionsProps {
    hidden?: boolean
    onSelect: (text: string) => void
    suggestions?: string[]
    agentType?: string | null
    className?: string
}

const Suggestions = ({
    className = '',
    hidden,
    onSelect,
    suggestions,
    agentType = AGENT_TYPE.GENERAL
}: SuggestionsProps) => {
    const { t } = useTranslation()
    const isSage = useIsSageTheme()

    const translatedSuggestions = t(
        isSage ? 'chat.sageSuggestions' : 'chat.suggestions',
        {
            returnObjects: true
        }
    ) as Partial<Record<AGENT_TYPE, string[]>>

    const fallbackSuggestions =
        translatedSuggestions?.[AGENT_TYPE.GENERAL] ?? []

    const suggestionsToRender =
        suggestions ??
        translatedSuggestions?.[
            (agentType as AGENT_TYPE) ?? AGENT_TYPE.GENERAL
        ] ??
        fallbackSuggestions

    if (hidden) return null

    const containerClasses = `hidden md:flex flex-col items-stretch gap-2 max-h-[200px] overflow-auto ${className}`

    const buttonClasses = `text-xs bg-transparent hover:bg-charcoal/10 dark:hover:bg-sky-blue/10 px-6 py-2 h-auto rounded-full text-[#4D6065] hover:text-black dark:hover:text-sky-blue hover:font-semibold justify-start transition-colors duration-200 ${isSage ? 'dark:text-[#A68A6B]' : ''}`

    return (
        <div className={containerClasses}>
            {suggestionsToRender.map((item) => (
                <Button
                    key={item}
                    className={buttonClasses}
                    onClick={() => onSelect(item)}
                >
                    {item}
                </Button>
            ))}
        </div>
    )
}

export default Suggestions
