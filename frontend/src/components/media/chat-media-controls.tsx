import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { type ChatMediaModel } from '@/constants/media-models'
import { getMediaTypeConfig } from '@/constants/media-type-config'
import { useMediaModels } from '@/hooks/use-media-models'
import { type ChatMediaPreference } from '@/typings/agent'
import { Button } from '../ui/button'
import { Icon } from '../ui/icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '../ui/dropdown-menu'

type Props = {
    disabled?: boolean
    mediaPreference: ChatMediaPreference
    onModelSelect: (model: ChatMediaModel) => void
    onClear?: () => void
    showCancel?: boolean
}

const ChatMediaControls = ({
    disabled,
    mediaPreference,
    onModelSelect,
    onClear,
    showCancel = true
}: Props) => {
    const { t } = useTranslation()
    const { getModelsForMediaType } = useMediaModels()

    const typeConfig = getMediaTypeConfig(mediaPreference.type)
    const modelsForType = useMemo(
        () => getModelsForMediaType(mediaPreference.type),
        [mediaPreference.type, getModelsForMediaType]
    )

    if (!mediaPreference.enabled) return null

    const shouldShowCancel = showCancel && typeof onClear === 'function'

    const selectedModel =
        modelsForType.find(
            (m) => m.model_name === mediaPreference.model_name
        ) || modelsForType[0]

    const iconName = typeConfig.icon
    const typeLabel = t('media.controls.modelLabel', {
        type: t(`media.types.${mediaPreference.type}`)
    })

    return (
        <div className="flex items-center gap-2 flex-shrink-0">
            <div
                className={`flex items-center gap-[6px] rounded-[8px] px-2 py-[3px] bg-blue-gradient text-sky-900 dark:text-black`}
            >
                <Icon name={iconName} className={`text-black size-5`} />
                {shouldShowCancel && (
                    <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        className={`h-4 w-4 rounded-full p-0`}
                        disabled={disabled}
                        onClick={onClear}
                    >
                        <Icon name="cancel" className={`size-4 stroke-black`} />
                    </Button>
                )}
            </div>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        type="button"
                        variant="secondary"
                        size="icon"
                        className={`text-xs px-4 w-auto h-7 rounded-full cursor-pointer flex-shrink-0 ${'border border-firefly dark:border-sky-blue-2 text-firefly dark:text-sky-blue-2'}`}
                        disabled={disabled}
                        title={typeLabel}
                    >
                        <Icon
                            name={selectedModel?.icon}
                            className="inline md:hidden size-4"
                        />
                        <span className="hidden md:inline truncate max-w-[120px]">
                            {selectedModel
                                ? t(selectedModel.label)
                                : t('media.controls.selectModel')}
                        </span>
                        <Icon
                            name="arrow-down"
                            className="fill-firefly dark:fill-sky-blue-2"
                        />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-[240px] p-2">
                    {modelsForType.map((model) => (
                        <DropdownMenuItem
                            key={model.id}
                            className="cursor-pointer flex-col items-start gap-1 py-2"
                            onClick={() => onModelSelect(model)}
                        >
                            <div className="flex items-center gap-2">
                                <span className="font-semibold text-black">
                                    {t(model.label)}
                                </span>
                                {model.model_name ===
                                    mediaPreference.model_name && (
                                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                                        {t('media.controls.selected')}
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-grey-1">
                                {t(model.description)}
                            </p>
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    )
}

export default ChatMediaControls
