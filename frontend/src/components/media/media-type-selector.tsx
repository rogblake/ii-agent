import { useTranslation } from 'react-i18next'

import { type ChatMediaType } from '@/constants/media-type-config'
import { Icon } from '../ui/icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '../ui/dropdown-menu'
import ButtonIcon from '../button-icon'

const MEDIA_TYPES: { type: ChatMediaType; icon: string; label: string }[] = [
    { type: 'image', icon: 'gallery', label: 'media.types.image' },
    { type: 'infographic', icon: 'mode-infographic', label: 'media.types.infographic' },
    { type: 'poster', icon: 'mode-poster', label: 'media.types.poster' },
    {
        type: 'storybook',
        icon: 'mode-storybook',
        label: 'media.types.storybook'
    },
    { type: 'video', icon: 'mode-video', label: 'media.types.video' }
]

type Props = {
    disabled?: boolean
    onMediaTypeSelect: (type: ChatMediaType) => void
}

const MediaTypeSelector = ({ disabled, onMediaTypeSelect }: Props) => {
    const { t } = useTranslation()

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <ButtonIcon
                    disabled={disabled}
                    name="mode"
                    iconClassName="text-black"
                />
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-[200px] p-2">
                {MEDIA_TYPES.map((mediaType) => (
                    <DropdownMenuItem
                        key={mediaType.type}
                        className="cursor-pointer flex items-center gap-2 py-2"
                        onClick={() => onMediaTypeSelect(mediaType.type)}
                    >
                        <Icon name={mediaType.icon} className="size-4" />
                        <span className="font-medium">
                            {t(mediaType.label)}
                        </span>
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

export default MediaTypeSelector
