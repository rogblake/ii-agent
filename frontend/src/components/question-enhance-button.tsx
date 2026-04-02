import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import ButtonIcon from './button-icon'
import { Icon } from './ui/icon'
import { useTranslation } from 'react-i18next'

interface EnhanceButtonProps {
  isGenerating: boolean
  disabled: boolean
  onClick?: () => void
}

const EnhanceButton = ({ isGenerating, disabled, onClick }: EnhanceButtonProps) => {
  const { t } = useTranslation()

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {isGenerating ? (
          <Icon name="loading" className="animate-spin size-7 fill-black dark:fill-white" />
        ) : (
          <ButtonIcon name="magic-pen" onClick={onClick} disabled={disabled} />
        )}
      </TooltipTrigger>
      <TooltipContent>{t('question.enhancePrompt')}</TooltipContent>
    </Tooltip>
  )
}

export default EnhanceButton
