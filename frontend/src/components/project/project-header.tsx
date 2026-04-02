import { useState } from 'react'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import { Icon } from '../ui/icon'

export type ProjectTab =
    | 'code'
    | 'terminal'
    | 'database'
    | 'domain'
    | 'integrations'
    | 'branding'
    | 'secrets'
    | 'authentication'

interface TabConfig {
    id: ProjectTab
    labelKey: string
    icon: string
    titleKey: string
    descriptionKey: string
}

interface ProjectHeaderProps {
    activeTab?: ProjectTab
    onTabChange?: (tab: ProjectTab) => void
}

const ProjectHeader = ({
    activeTab: controlledTab,
    onTabChange
}: ProjectHeaderProps = {}) => {
    const { t } = useTranslation()
    const [internalTab, setInternalTab] = useState<ProjectTab>('code')

    const activeTab = controlledTab ?? internalTab
    const setActiveTab = onTabChange ?? setInternalTab
    const tabs: TabConfig[] = [
        {
            id: 'code',
            labelKey: 'project.header.tabs.code.label',
            icon: 'code',
            titleKey: 'project.header.tabs.code.title',
            descriptionKey: 'project.header.tabs.code.description'
        },
        {
            id: 'terminal',
            labelKey: 'project.header.tabs.terminal.label',
            icon: 'terminal',
            titleKey: 'project.header.tabs.terminal.title',
            descriptionKey: 'project.header.tabs.terminal.description'
        },
        {
            id: 'database',
            labelKey: 'project.header.tabs.database.label',
            icon: 'database',
            titleKey: 'project.header.tabs.database.title',
            descriptionKey: 'project.header.tabs.database.description'
        },
        {
            id: 'domain',
            labelKey: 'project.header.tabs.domain.label',
            icon: 'globe',
            titleKey: 'project.header.tabs.domain.title',
            descriptionKey: 'project.header.tabs.domain.description'
        },
        {
            id: 'integrations',
            labelKey: 'project.header.tabs.integrations.label',
            icon: 'connector',
            titleKey: 'project.header.tabs.integrations.title',
            descriptionKey: 'project.header.tabs.integrations.description'
        },
        {
            id: 'secrets',
            labelKey: 'project.header.tabs.secrets.label',
            icon: 'secret',
            titleKey: 'project.header.tabs.secrets.title',
            descriptionKey: 'project.header.tabs.secrets.description'
        }
    ]

    const currentTab = tabs.find((tab) => tab.id === activeTab)

    const getTabClasses = (tabId: ProjectTab) => {
        const isActive = activeTab === tabId
        return clsx(
            'flex items-center gap-[6px] px-4 py-2 rounded-lg text-sm transition-colors cursor-pointer',
            {
                'bg-firefly dark:bg-sky-blue text-sky-blue-2 dark:text-charcoal':
                    isActive,
                'bg-firefly/10 dark:bg-[#BEE6F01A] text-charcoal dark:text-sky-blue':
                    !isActive
            }
        )
    }

    return (
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex flex-col flex-1">
                <h2 className="font-semibold text-base">
                    {currentTab ? t(currentTab.titleKey) : null}
                </h2>
                <p className="text-gray-400 text-sm">
                    {currentTab ? t(currentTab.descriptionKey) : null}
                </p>
            </div>
            <div className="flex items-center gap-3">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        className={getTabClasses(tab.id)}
                        onClick={() => setActiveTab(tab.id)}
                    >
                        <Icon
                            name={tab.icon}
                            className={clsx('size-4', {
                                'stroke-sky-blue-2 dark:stroke-charcoal':
                                    tab.icon !== 'database' &&
                                    tab.icon !== 'connector' &&
                                    activeTab === tab.id,
                                'stroke-black dark:stroke-sky-blue':
                                    tab.icon !== 'database' &&
                                    tab.icon !== 'connector' &&
                                    activeTab !== tab.id,
                                'fill-sky-blue-2 dark:fill-charcoal':
                                    (tab.icon === 'database' ||
                                        tab.icon === 'connector') &&
                                    activeTab === tab.id,
                                'fill-black dark:fill-sky-blue':
                                    (tab.icon === 'database' ||
                                        tab.icon === 'connector') &&
                                    activeTab !== tab.id
                            })}
                        />
                        {t(tab.labelKey)}
                    </button>
                ))}
            </div>
        </div>
    )
}

export default ProjectHeader
