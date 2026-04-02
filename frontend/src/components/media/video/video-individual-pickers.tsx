import { useMemo, useState } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'

import { Icon } from '../../ui/icon'
import { Popover, PopoverContent, PopoverTrigger } from '../../ui/popover'
import { cn } from '@/lib/utils'
import type {
    VideoDuration,
    VideoResolution,
    VideoAspectRatio
} from '@/typings/agent'
import {
    VIDEO_DURATION_OPTIONS,
    VIDEO_RESOLUTION_OPTIONS
} from '@/constants/video-models'

// All aspect ratio options for video
const VIDEO_ASPECT_RATIO_OPTIONS: { value: VideoAspectRatio; label: string }[] =
    [
        { value: '16:9', label: '16:9' },
        { value: '9:16', label: '9:16' }
    ]

// Calculate dimensions for aspect ratio preview
const calculateAspectRatioDimensions = (
    ratio: string
): {
    width: number
    height: number
} => {
    const [width, height] = ratio.split(':').map(Number)
    const maxSize = 48
    const aspectRatioValue = width / height

    if (aspectRatioValue > 1) {
        return { width: maxSize, height: maxSize / aspectRatioValue }
    }
    return { width: maxSize * aspectRatioValue, height: maxSize }
}

// ============================================
// Video Duration Picker
// ============================================
interface VideoDurationPickerProps {
    duration: VideoDuration
    onDurationChange: (duration: VideoDuration) => void
    disabled?: boolean
    isPro?: boolean
    supportedDurations?: VideoDuration[]
    className?: string
}

export function VideoDurationPicker({
    duration,
    onDurationChange,
    disabled,
    isPro = false,
    supportedDurations,
    className
}: VideoDurationPickerProps): ReactElement {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const durations = useMemo(() => {
        const supported =
            supportedDurations ?? VIDEO_DURATION_OPTIONS.map((d) => d.value)
        return VIDEO_DURATION_OPTIONS.filter((d) => supported.includes(d.value))
    }, [supportedDurations])

    const handleDurationChange = (dur: VideoDuration): void => {
        const durOption = durations.find((d) => d.value === dur)
        if (durOption?.isPro && !isPro) return
        onDurationChange(dur)
        setOpen(false)
    }

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-[#2c2e2d] text-white',
                        'hover:bg-[#3a3c3b] transition-colors',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.videoPickers.durationLabel')}:</span>
                    <span>{duration}</span>
                </button>
            </PopoverTrigger>
            <PopoverContent
                className="w-40 p-0 !bg-white border border-grey dark:border-grey/40 shadow-lg"
                align="start"
                sideOffset={8}
            >
                <div className="p-3">
                    <div className="text-xs font-medium text-black mb-2">
                        {t('media.videoPickers.durationLabel')}
                    </div>
                    <div className="flex flex-col gap-1.5">
                        {durations.map((dur) => {
                            const isDisabled = dur.isPro && !isPro
                            return (
                                <button
                                    key={dur.value}
                                    type="button"
                                    onClick={() =>
                                        handleDurationChange(dur.value)
                                    }
                                    disabled={isDisabled}
                                    className={cn(
                                        'cursor-pointer flex items-center justify-between px-3 py-2 text-xs rounded-md transition-colors',
                                        'bg-transparent text-black/70 hover:bg-grey-3',
                                        isDisabled &&
                                            'opacity-50 cursor-not-allowed'
                                    )}
                                >
                                    <span>{dur.label}</span>
                                    <div className="ml-auto flex items-center justify-end gap-2">
                                        {dur.isPro && (
                                            <span className="px-1.5 py-0.5 text-[10px] rounded bg-amber-100 text-amber-700">
                                                {t(
                                                    'media.videoPickers.proBadge'
                                                )}
                                            </span>
                                        )}
                                        <span className="w-4 flex justify-end">
                                            {duration === dur.value && (
                                                <Icon
                                                    name="tick"
                                                    className="size-4 fill-black"
                                                />
                                            )}
                                        </span>
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    )
}

// ============================================
// Video Resolution Picker
// ============================================
interface VideoResolutionPickerProps {
    resolution: VideoResolution
    onResolutionChange: (resolution: VideoResolution) => void
    disabled?: boolean
    isPro?: boolean
    supportedResolutions?: VideoResolution[]
    className?: string
}

export function VideoResolutionPicker({
    resolution,
    onResolutionChange,
    disabled,
    isPro = false,
    supportedResolutions,
    className
}: VideoResolutionPickerProps): ReactElement {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const resolutions = useMemo(() => {
        const supported =
            supportedResolutions ?? VIDEO_RESOLUTION_OPTIONS.map((r) => r.value)
        return VIDEO_RESOLUTION_OPTIONS.filter((r) =>
            supported.includes(r.value)
        )
    }, [supportedResolutions])

    const handleResolutionChange = (res: VideoResolution): void => {
        const resOption = resolutions.find((r) => r.value === res)
        if (resOption?.isPro && !isPro) return
        onResolutionChange(res)
        setOpen(false)
    }

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-[#2c2e2d] text-white',
                        'hover:bg-[#3a3c3b] transition-colors',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.videoPickers.resolutionLabel')}:</span>
                    <span>{resolution}</span>
                </button>
            </PopoverTrigger>
            <PopoverContent
                className="w-40 p-0 !bg-white border border-grey dark:border-grey/40 shadow-lg"
                align="start"
                sideOffset={8}
            >
                <div className="p-3">
                    <div className="text-xs font-medium text-black mb-2">
                        {t('media.videoPickers.resolutionLabel')}
                    </div>
                    <div className="flex flex-col gap-1.5">
                        {resolutions.map((res) => {
                            const isDisabled = res.isPro && !isPro
                            return (
                                <button
                                    key={res.value}
                                    type="button"
                                    onClick={() =>
                                        handleResolutionChange(res.value)
                                    }
                                    disabled={isDisabled}
                                    className={cn(
                                        'cursor-pointer flex items-center justify-between px-3 py-2 text-xs rounded-md transition-colors',
                                        'bg-transparent text-black/70 hover:bg-grey-3',
                                        isDisabled &&
                                            'opacity-50 cursor-not-allowed'
                                    )}
                                >
                                    <span>{res.label}</span>
                                    <div className="ml-auto flex items-center justify-end gap-2">
                                        {res.isPro && (
                                            <span className="px-1.5 py-0.5 text-[10px] rounded bg-amber-100 text-amber-700">
                                                {t(
                                                    'media.videoPickers.proBadge'
                                                )}
                                            </span>
                                        )}
                                        <span className="w-4 flex justify-end">
                                            {resolution === res.value && (
                                                <Icon
                                                    name="tick"
                                                    className="size-4 fill-black"
                                                />
                                            )}
                                        </span>
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    )
}

// ============================================
// Video Aspect Ratio Picker
// ============================================
interface VideoAspectRatioPickerProps {
    aspectRatio: VideoAspectRatio
    onAspectRatioChange: (aspectRatio: VideoAspectRatio) => void
    disabled?: boolean
    supportedAspectRatios?: VideoAspectRatio[]
    className?: string
}

export function VideoAspectRatioPicker({
    aspectRatio,
    onAspectRatioChange,
    disabled,
    supportedAspectRatios,
    className
}: VideoAspectRatioPickerProps): ReactElement {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const aspectRatios = useMemo(() => {
        const supported =
            supportedAspectRatios ??
            VIDEO_ASPECT_RATIO_OPTIONS.map((a) => a.value)
        return VIDEO_ASPECT_RATIO_OPTIONS.filter((a) =>
            supported.includes(a.value)
        )
    }, [supportedAspectRatios])

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-[#2c2e2d] text-white',
                        'hover:bg-[#3a3c3b] transition-colors',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.videoPickers.ratioLabel')}:</span>
                    <span>{aspectRatio}</span>
                </button>
            </PopoverTrigger>
            <PopoverContent
                className="w-auto p-0 !bg-white border border-grey dark:border-grey/40 shadow-lg"
                align="start"
                sideOffset={8}
            >
                <div className="p-3">
                    <div className="text-xs font-medium text-black mb-3">
                        {t('media.videoPickers.aspectRatioLabel')}
                    </div>
                    <div className="flex gap-3">
                        {aspectRatios.map((ratio) => {
                            const dimensions = calculateAspectRatioDimensions(
                                ratio.value
                            )
                            return (
                                <button
                                    key={ratio.value}
                                    type="button"
                                    onClick={() => {
                                        onAspectRatioChange(ratio.value)
                                        setOpen(false)
                                    }}
                                    className="cursor-pointer flex flex-col items-center gap-1"
                                >
                                    <div
                                        className={cn(
                                            'rounded-lg transition-all flex items-center justify-center font-light border-2',
                                            aspectRatio === ratio.value
                                                ? 'bg-white border-black text-black text-xs'
                                                : 'bg-white border-grey text-black text-xs hover:border-grey-2'
                                        )}
                                        style={{
                                            width: `${dimensions.width}px`,
                                            height: `${dimensions.height}px`
                                        }}
                                    >
                                        {aspectRatio === ratio.value ? (
                                            <Icon
                                                name="tick"
                                                className="size-4 fill-black"
                                            />
                                        ) : (
                                            <span className="text-[10px]">
                                                {ratio.label}
                                            </span>
                                        )}
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    )
}

// ============================================
// Video Audio Toggle Picker
// ============================================
interface VideoAudioPickerProps {
    audioIncluded: boolean
    onAudioChange: (audioIncluded: boolean) => void
    disabled?: boolean
    supportsAudio?: boolean
    className?: string
}

export function VideoAudioPicker({
    audioIncluded,
    onAudioChange,
    disabled,
    supportsAudio = true,
    className
}: VideoAudioPickerProps): ReactElement | null {
    const { t } = useTranslation()
    if (!supportsAudio) return null

    return (
        <button
            type="button"
            disabled={disabled}
            onClick={() => onAudioChange(!audioIncluded)}
            className={cn(
                'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium transition-colors bg-[#2c2e2d] text-white',
                'hover:bg-[#3a3c3b]',
                disabled && 'opacity-50 cursor-not-allowed',
                className
            )}
        >
            <Icon
                name={audioIncluded ? 'volume-high' : 'volume-slash'}
                className={cn(
                    'size-3.5',
                    audioIncluded ? 'fill-white' : 'fill-white/60'
                )}
            />
            <span>{t('media.videoPickers.audioLabel')}</span>
            <span
                className={cn(
                    'text-[10px] px-1 py-0.5 rounded',
                    audioIncluded
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                )}
            >
                {audioIncluded
                    ? t('media.videoPickers.stateOn')
                    : t('media.videoPickers.stateOff')}
            </span>
        </button>
    )
}

// ============================================
// Video Multishot Toggle Picker
// ============================================
interface VideoMultishotPickerProps {
    multishotMode: boolean
    onMultishotChange: (multishotMode: boolean) => void
    disabled?: boolean
    supportsMultishot?: boolean
    className?: string
}

export function VideoMultishotPicker({
    multishotMode,
    onMultishotChange,
    disabled,
    supportsMultishot = true,
    className
}: VideoMultishotPickerProps): ReactElement | null {
    const { t } = useTranslation()
    if (!supportsMultishot) return null

    return (
        <button
            type="button"
            disabled={disabled}
            onClick={() => onMultishotChange(!multishotMode)}
            className={cn(
                'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium transition-colors bg-[#2c2e2d] text-white',
                'hover:bg-[#3a3c3b]',
                disabled && 'opacity-50 cursor-not-allowed',
                className
            )}
        >
            <Icon
                name="video-play"
                className={cn(
                    'size-3.5',
                    multishotMode ? 'fill-white' : 'fill-white/60'
                )}
            />
            <span>{t('media.videoPickers.multishotLabel')}</span>
            <span
                className={cn(
                    'text-[10px] px-1 py-0.5 rounded',
                    multishotMode
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                )}
            >
                {multishotMode
                    ? t('media.videoPickers.stateOn')
                    : t('media.videoPickers.stateOff')}
            </span>
        </button>
    )
}
