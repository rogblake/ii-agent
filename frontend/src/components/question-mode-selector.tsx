import { Icon } from './ui/icon'
import { QUESTION_MODE } from '@/typings'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

interface ModeSelectorProps {
    selectedMode: QUESTION_MODE
    hide?: boolean
    onSelect: (mode: QUESTION_MODE) => void
}

const ModeSelector = ({ selectedMode, hide, onSelect }: ModeSelectorProps) => {
    const { t } = useTranslation()
    const isSage = useIsSageTheme()

    if (hide) return null

    return (
        <div className="hidden md:flex items-end">
            <button
                onClick={() => onSelect(QUESTION_MODE.CHAT)}
                className={cn(
                    'flex items-center gap-x-[6px] px-4 py-2 rounded-tl-xl rounded-tr-xl text-xs cursor-pointer',
                    selectedMode === QUESTION_MODE.CHAT
                        ? 'bg-charcoal dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black font-semibold'
                        : 'bg-charcoal/10 dark:bg-sky-blue-2/10 text-black/50 dark:text-white/50',
                    isSage &&
                        (selectedMode === QUESTION_MODE.CHAT
                            ? 'dark:bg-sky-blue-3'
                            : 'dark:bg-sky-blue-3/10 text-black dark:text-white')
                )}
            >
                <Icon
                    name="chat-fill"
                    className={cn(
                        `size-4 ${selectedMode === QUESTION_MODE.CHAT ? 'fill-sky-blue-2 dark:fill-black' : 'fill-black/30 dark:fill-white/30'}`,
                        isSage &&
                            (selectedMode === QUESTION_MODE.CHAT
                                ? 'dark:fill-black'
                                : 'dark:fill-white')
                    )}
                />
                <span className="hidden md:inline">
                    {t('question.mode.chat')}
                </span>
            </button>
            <button
                onClick={() => onSelect(QUESTION_MODE.AGENT)}
                className={cn(
                    'flex items-center gap-x-[6px] px-4 py-2 rounded-tl-xl rounded-tr-xl text-xs cursor-pointer',
                    selectedMode === QUESTION_MODE.AGENT
                        ? 'bg-charcoal dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black font-semibold'
                        : 'bg-charcoal/10 dark:bg-sky-blue-2/10 text-black/50 dark:text-white/50',
                    isSage &&
                        (selectedMode === QUESTION_MODE.AGENT
                            ? 'dark:bg-sky-blue-3'
                            : 'dark:bg-sky-blue-3/10 text-black dark:text-white')
                )}
            >
                <Icon
                    name="agent-fill"
                    className={cn(
                        `size-4 ${selectedMode === QUESTION_MODE.AGENT ? 'fill-sky-blue-2 dark:fill-black' : 'fill-black/30 dark:fill-white/30'}`,
                        isSage &&
                            (selectedMode === QUESTION_MODE.AGENT
                                ? 'dark:fill-black'
                                : 'dark:fill-white')
                    )}
                />
                <span className="hidden md:inline">
                    {t('question.mode.agent')}
                </span>
            </button>
        </div>
    )
}

export default ModeSelector
