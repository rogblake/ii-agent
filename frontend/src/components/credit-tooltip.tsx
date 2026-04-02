import { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { Icon } from './ui/icon'
import { Button } from './ui/button'

interface CreditTooltipProps {
    credits: number
    bonusCredits?: number
    children: ReactNode
    hideViewUsage?: boolean
}

const CreditTooltip = ({
    credits,
    bonusCredits = 0,
    children,
    hideViewUsage
}: CreditTooltipProps) => {
    const navigate = useNavigate()
    const { t } = useTranslation()

    const formatCredit = (value: number) => {
        const rounded = Math.round(value)
        return (rounded === 0 ? 0 : rounded).toLocaleString('en-US')
    }

    const handleViewUsage = () => {
        navigate('/settings/usage')
    }

    return (
        <Tooltip>
            <TooltipTrigger asChild>{children}</TooltipTrigger>
            <TooltipContent side="top">
                <div className="w-[160px] text-sm flex flex-col items-start justify-between gap-1">
                    <div className="w-full flex items-center justify-between gap-6">
                        <span className="font-semibold flex-1">
                            {t('credit.tooltip.credit')}
                        </span>
                        <span>{formatCredit(credits)}</span>
                    </div>
                    <div className="w-full flex items-center justify-between gap-6">
                        <span className="font-semibold flex-1">
                            {t('credit.tooltip.bonusCredit')}
                        </span>
                        <span>{formatCredit(bonusCredits)}</span>
                    </div>
                    {!hideViewUsage && (
                        <Button className="!p-0" onClick={handleViewUsage}>
                            {t('credit.tooltip.viewUsage')}{' '}
                            <Icon
                                name="arrow-right-2"
                                className="size-4 stroke-black"
                            />
                        </Button>
                    )}
                </div>
            </TooltipContent>
        </Tooltip>
    )
}

export default CreditTooltip
