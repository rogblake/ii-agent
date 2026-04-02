import { Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from './ui/button'
import { Icon } from './ui/icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from './ui/dropdown-menu'
import { BUILD_MODE } from '@/typings'

interface BuildModeConfig {
    labelKey: string
    descriptionKey: string
    icon: string
    buttonClass: string
    iconClass: string
}

const BUILD_MODE_CONFIG: Record<BUILD_MODE, BuildModeConfig> = {
    [BUILD_MODE.BUILD]: {
        labelKey: 'buildModeDropdown.modes.build.label',
        descriptionKey: 'buildModeDropdown.modes.build.description',
        icon: 'build-2',
        buttonClass:
            'border-firefly text-firefly dark:border-sky-blue dark:text-sky-blue',
        iconClass: 'fill-firefly dark:fill-sky-blue'
    },
    [BUILD_MODE.DESIGN]: {
        labelKey: 'buildModeDropdown.modes.design.label',
        descriptionKey: 'buildModeDropdown.modes.design.description',
        icon: 'design-3',
        buttonClass: 'border-orange text-orange',
        iconClass: 'fill-orange'
    },
    [BUILD_MODE.PLAN]: {
        labelKey: 'buildModeDropdown.modes.plan.label',
        descriptionKey: 'buildModeDropdown.modes.plan.description',
        icon: 'plan',
        buttonClass:
            'border-pewter dark:border-mist text-pewter dark:text-mist',
        iconClass: 'fill-pewter dark:fill-mist'
    },
    [BUILD_MODE.HELP]: {
        labelKey: 'buildModeDropdown.modes.help.label',
        descriptionKey: 'buildModeDropdown.modes.help.description',
        icon: 'help-2',
        buttonClass: 'border-green-2 text-green-2',
        iconClass: 'fill-green-2'
    }
}

// Default modes that are currently available to users
const DEFAULT_AVAILABLE_MODES = [
    BUILD_MODE.BUILD,
    BUILD_MODE.DESIGN,
    BUILD_MODE.PLAN
]

// Modes available on landing page (no DESIGN option - only show in chatbox)
export const LANDING_AVAILABLE_MODES = [BUILD_MODE.BUILD, BUILD_MODE.PLAN]

interface BuildModeDropdownProps {
    selectedMode: BUILD_MODE
    onSelect: (mode: BUILD_MODE) => void
    disabled?: boolean
    availableModes?: BUILD_MODE[]
}

const BuildModeDropdown = ({
    selectedMode,
    onSelect,
    disabled,
    availableModes = DEFAULT_AVAILABLE_MODES
}: BuildModeDropdownProps) => {
    const { t } = useTranslation()
    const currentMode = BUILD_MODE_CONFIG[selectedMode]

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild disabled={disabled}>
                <Button
                    variant="secondary"
                    size="icon"
                    className={`text-xs px-3 w-auto h-7 bg-transparent rounded-full cursor-pointer gap-2 border ${currentMode.buttonClass}`}
                    disabled={disabled}
                >
                    <Icon
                        name={currentMode.icon}
                        className={`size-4 ${currentMode.iconClass}`}
                    />
                    <span className="hidden md:inline">
                        {t(currentMode.labelKey)}
                    </span>
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                className="w-[360px] p-0"
                align="start"
                sideOffset={8}
            >
                {Object.entries(BUILD_MODE_CONFIG)
                    .filter(([mode]) =>
                        availableModes.includes(mode as BUILD_MODE)
                    )
                    .map(([mode, config]) => (
                        <DropdownMenuItem
                            key={mode}
                            onClick={() => onSelect(mode as BUILD_MODE)}
                            className="cursor-pointer flex items-start gap-[6px] p-4"
                        >
                            <Icon
                                name={config.icon}
                                className="size-5 fill-black mt-0.5 shrink-0"
                            />
                            <div className="flex-1 min-w-0">
                                <div className="text-black text-sm">
                                    {t(config.labelKey)}
                                </div>
                                <div className="text-xs text-black/[0.56] mt-1">
                                    {t(config.descriptionKey)}
                                </div>
                            </div>
                            {selectedMode === mode && (
                                <Check className="size-5 text-black mt-0.5 shrink-0" />
                            )}
                        </DropdownMenuItem>
                    ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

export default BuildModeDropdown
