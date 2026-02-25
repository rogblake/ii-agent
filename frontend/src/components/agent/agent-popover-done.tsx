import dayjs from 'dayjs'
import findLast from 'lodash/findLast'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
    Popover,
    PopoverContent,
    PopoverTrigger
} from '@/components/ui/popover'
import {
    selectBuildMode,
    selectIsCompleted,
    selectMessages,
    useAppSelector
} from '@/state'
import { BUILD_MODE } from '@/typings/agent'
import { Message, TOOL } from '@/typings'
import { Icon } from '../ui/icon'
import { useIsMobile } from '@/hooks/use-mobile'

const AgentPopoverDone = () => {
    const { t } = useTranslation()
    const isMobile = useIsMobile()
    const [open, setOpen] = useState(false)
    const messages = useAppSelector(selectMessages)
    const isCompleted = useAppSelector(selectIsCompleted)
    const buildMode = useAppSelector(selectBuildMode)

    const plans = useMemo(
        () =>
            findLast(
                messages,
                (m: Message) => m?.action?.type === TOOL.TODO_WRITE
            )?.action?.data?.tool_input?.todos || [],
        [messages]
    )

    if (buildMode === BUILD_MODE.DESIGN) return null
    if (!plans || plans.length === 0 || !isCompleted || isMobile) return null

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger>
                <div className="bg-firefly shadow-btn dark:bg-sky-blue rounded-full flex items-center justify-center cursor-pointer gap-3 py-[6px] px-4">
                    <Icon
                        name="brain"
                        className="text-sky-blue-2 dark:text-black size-5 md:size-7"
                    />
                    <span className="text-sm md:text-base font-semibold text-sky-blue-2 dark:text-black">
                        {t('agentPopoverDone.trigger')}
                    </span>
                </div>
            </PopoverTrigger>
            <PopoverContent
                align="end"
                className="bg-white rounded-xl p-0 text-black w-[320px] border-none dark:border shadow-[0px_4px_24px_rgba(0,0,0,0.16)]"
            >
                <div className="flex items-center justify-between p-4 pb-0">
                    <span className="text-base font-semibold">
                        {t('agentPopoverDone.title')}
                    </span>
                    <button
                        className="cursor-pointer"
                        onClick={() => setOpen(false)}
                    >
                        <Icon name="cancel" className="stroke-black" />
                    </button>
                </div>
                <div className="flex mt-4 px-4">
                    <p className="py-[6px] text-center px-4 text-[#666600] bg-[#666600]/10 rounded-full font-semibold">
                        {dayjs().format('HH:mm')}
                    </p>
                </div>
                <div className="mt-3 space-y-3 max-h-[400px] overflow-auto px-4 pb-4">
                    {Array.isArray(plans) &&
                        plans?.map((plan) => (
                            <div
                                key={plan.id}
                                className="flex items-start gap-x-[6px]"
                            >
                                <Icon name="tick-circle" />
                                <span className="flex-1">{plan.content}</span>
                            </div>
                        ))}
                </div>
            </PopoverContent>
        </Popover>
    )
}

export default AgentPopoverDone
