import { useMemo } from 'react'
import clsx from 'clsx'
import { useLocation } from 'react-router'

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import {
    selectActiveTab,
    setActiveTab,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { TAB } from '@/typings/agent'
import { useTranslation } from 'react-i18next'

export type ChatOption = 'chat' | 'design' | 'files'

interface AgentTabMobileProps {
    isShowChat: boolean
    onToggleChat: (value: boolean) => void
    activeChatOption: ChatOption
    onChatOptionChange: (option: ChatOption) => void
    sessionId?: string
    projectId?: string | null
}

const AgentTabMobile = ({
    isShowChat,
    onToggleChat,
    activeChatOption,
    onChatOptionChange,
    sessionId,
    projectId
}: AgentTabMobileProps) => {
    const location = useLocation()
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const activeTab = useAppSelector(selectActiveTab)

    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    const chatOptionLabel = useMemo(() => {
        switch (activeChatOption) {
            case 'design':
                return t('agentTab.options.design')
            case 'files':
                return t('agentTab.options.files')
            case 'chat':
            default:
                return t('agentTab.options.chat')
        }
    }, [activeChatOption, t])

    const handleSelectTab = (tab: TAB) => {
        onToggleChat(false)
        dispatch(setActiveTab(tab))
    }

    const handleChatOptionSelect = (option: ChatOption) => {
        onChatOptionChange(option)
        onToggleChat(true)
    }

    const shouldShowProjectTab = useMemo(() => {
        if (isShareMode) {
            return false
        }
        return Boolean(sessionId && projectId)
    }, [isShareMode, sessionId, projectId])

    const tabLabel = useMemo(() => {
        switch (activeTab) {
            case TAB.BUILD:
                return t('agentTab.tabs.build')
            case TAB.CODE:
                return t('agentTab.tabs.code')
            case TAB.RESULT:
                return t('agentTab.tabs.result')
            case TAB.PROJECT:
                return t('agentTab.tabs.project')
            default:
                return activeTab
        }
    }, [activeTab, t])

    return (
        <div className="px-3 flex md:hidden items-center gap-3 mt-1">
            <DropdownMenu>
                <DropdownMenuTrigger
                    className={clsx(
                        `flex-1 text-sm cursor-pointer flex justify-between md:hidden px-4 py-[6px] rounded-3xl`,
                        {
                            'border border-black text-black dark:border-sky-blue dark:text-sky-blue':
                                isShowChat,
                            'bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-black':
                                !isShowChat
                        }
                    )}
                >
                    <span className="capitalize font-semibold">{tabLabel}</span>
                    <Icon
                        name="arrow-down"
                        className={clsx('size-5', {
                            'fill-black dark:fill-white': isShowChat,
                            'fill-sky-blue-2 dark:fill-black': !isShowChat
                        })}
                    />
                </DropdownMenuTrigger>
                <DropdownMenuContent
                    align="end"
                    className="w-[185px] px-4 py-2"
                >
                    {/* <DropdownMenuItem
                        className="px-0 py-2"
                        onClick={() => handleSelectTab(TAB.BUILD)}
                    >
                        <Icon name="build" className="size-5 stroke-black" />
                        {t('agentTab.tabs.build')}
                    </DropdownMenuItem> */}
                    <DropdownMenuItem
                        disabled
                        className="px-0 py-2"
                        onClick={() => handleSelectTab(TAB.CODE)}
                    >
                        <Icon name="code-2" className="size-5 stroke-black" />
                        {t('agentTab.tabs.code')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                        className="px-0 py-2"
                        onClick={() => handleSelectTab(TAB.RESULT)}
                    >
                        <Icon name="ai-magic" className="size-5 stroke-black" />
                        {t('agentTab.tabs.result')}
                    </DropdownMenuItem>
                    {shouldShowProjectTab && (
                        <DropdownMenuItem
                            className="px-0 py-2"
                            onClick={() => handleSelectTab(TAB.PROJECT)}
                        >
                            <Icon
                                name="folder-open"
                                className="size-5 fill-black"
                            />
                            {t('agentTab.tabs.project')}
                        </DropdownMenuItem>
                    )}
                </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
                <DropdownMenuTrigger
                    className={clsx(
                        `flex-1 text-sm cursor-pointer flex justify-between md:hidden px-4 py-[6px] rounded-3xl`,
                        {
                            'border border-black text-black dark:border-sky-blue dark:text-sky-blue':
                                !isShowChat,
                            'bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-black':
                                isShowChat
                        }
                    )}
                >
                    <span className="capitalize font-semibold">
                        {chatOptionLabel}
                    </span>
                    <Icon
                        name="arrow-down"
                        className={clsx('size-5', {
                            'fill-black dark:fill-white': !isShowChat,
                            'fill-sky-blue-2 dark:fill-black': isShowChat
                        })}
                    />
                </DropdownMenuTrigger>
                <DropdownMenuContent
                    align="end"
                    className="w-[185px] px-4 py-2"
                >
                    <DropdownMenuItem
                        className="px-0 py-2"
                        onClick={() => handleChatOptionSelect('chat')}
                    >
                        <Icon name="chat" className="size-5 fill-black" />
                        {t('agentTab.options.chat')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                        disabled
                        className="px-0 py-2"
                        onClick={() => handleChatOptionSelect('design')}
                    >
                        <Icon name="design-2" className="size-5 fill-black" />
                        {t('agentTab.options.design')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                        className="px-0 py-2"
                        onClick={() => handleChatOptionSelect('files')}
                    >
                        <Icon
                            name="document-text"
                            className="size-5 fill-black"
                        />
                        {t('agentTab.options.files')}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    )
}

export default AgentTabMobile
