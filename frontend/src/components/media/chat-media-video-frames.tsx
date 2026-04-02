import {
    useRef,
    type ChangeEvent,
    type MouseEvent,
    type ReactElement
} from 'react'
import { useTranslation } from 'react-i18next'

import { type ChatMediaModel } from '@/constants/media-models'
import type { ChatMediaPreference, VideoFrameReference } from '@/typings/agent'
import { Loader2 } from 'lucide-react'
import { Icon } from '../ui/icon'

type ChatMediaVideoFramesProps = {
    mediaPreference: ChatMediaPreference
    currentVideoModel: ChatMediaModel | null
    onVideoFrameAdd?: (file: File, type: 'start' | 'end') => void
    uploadingVideoFrames?: Set<'start' | 'end'>
    onVideoFrameRemove?: (frameId: string) => void
    disabled?: boolean
    className?: string
}

type FrameSlotProps = {
    type: 'start' | 'end'
    frame?: VideoFrameReference
    disabled?: boolean
    isUploading?: boolean
    onUpload: (file: File, type: 'start' | 'end') => void
    onRemove?: (frameId: string) => void
}

const FrameSlot = ({
    type,
    frame,
    disabled,
    isUploading,
    onUpload,
    onRemove
}: FrameSlotProps) => {
    const { t } = useTranslation()
    const inputRef = useRef<HTMLInputElement>(null)
    const label =
        type === 'start'
            ? t('media.videoFrames.startLabel')
            : t('media.videoFrames.endLabel')
    const uploadAriaLabel = t('media.videoFrames.uploadAria', { label })
    const previewAlt = t('media.videoFrames.previewAlt', { label })
    const removeAriaLabel = t('media.videoFrames.removeAria', { label })

    const handleClick = () => {
        if (!disabled && !isUploading) {
            inputRef.current?.click()
        }
    }

    const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0]
        if (file) {
            onUpload(file, type)
            event.target.value = ''
        }
    }

    const handleRemove = (event: MouseEvent<HTMLButtonElement>) => {
        event.stopPropagation()
        if (frame) {
            onRemove?.(frame.id)
        }
    }

    return (
        <div className="relative group">
            <input
                ref={inputRef}
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
                disabled={disabled || isUploading}
            />
            <button
                type="button"
                onClick={handleClick}
                disabled={disabled || isUploading}
                className={[
                    'relative flex h-[60px] w-[100px] items-center justify-center rounded-xl',
                    'transition-colors',
                    frame
                        ? 'overflow-hidden bg-black/20'
                        : 'border-2 border-dashed border-charcoal dark:border-white/70 bg-white dark:bg-black/60 hover:border-white',
                    (disabled || isUploading) &&
                        'opacity-50 cursor-not-allowed',
                    !disabled && !isUploading && 'cursor-pointer'
                ]
                    .filter(Boolean)
                    .join(' ')}
                aria-label={uploadAriaLabel}
            >
                {frame ? (
                    <img
                        src={frame.url}
                        alt={previewAlt}
                        className="h-full w-full object-cover"
                    />
                ) : (
                    <div className="flex flex-col items-center gap-1">
                        <span className="text-2xl leading-none">+</span>
                        <span className="text-sm">{label}</span>
                    </div>
                )}
                {isUploading && (
                    <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-black/60">
                        <Loader2 className="size-5 text-white animate-spin" />
                    </div>
                )}
            </button>
            {frame && onRemove && !isUploading && !disabled && (
                <button
                    type="button"
                    onClick={handleRemove}
                    className="absolute -top-2 -right-2 rounded-full bg-red-2 p-0.5 text-white cursor-pointer"
                    aria-label={removeAriaLabel}
                >
                    <Icon name="close" className="size-3 fill-white" />
                </button>
            )}
        </div>
    )
}

const ChatMediaVideoFrames = ({
    mediaPreference,
    currentVideoModel,
    onVideoFrameAdd,
    uploadingVideoFrames,
    onVideoFrameRemove,
    disabled,
    className
}: ChatMediaVideoFramesProps): ReactElement | null => {
    if (
        mediaPreference.type !== 'video' ||
        !currentVideoModel ||
        !onVideoFrameAdd
    ) {
        return null
    }

    const frames = mediaPreference.video_frames ?? []
    const startFrame = frames.find((frame) => frame.type === 'start')
    const endFrame = frames.find((frame) => frame.type === 'end')
    const supportsStartFrame = currentVideoModel.supports_start_frame ?? true
    const supportsEndFrame = currentVideoModel.supports_end_frame ?? false
    const isStartUploading = uploadingVideoFrames?.has('start') ?? false
    const isEndUploading = uploadingVideoFrames?.has('end') ?? false

    if (!supportsStartFrame && !supportsEndFrame) {
        return null
    }

    const containerClassName = ['flex flex-wrap items-center gap-3', className]
        .filter(Boolean)
        .join(' ')

    return (
        <div className={containerClassName}>
            {supportsStartFrame && (
                <FrameSlot
                    type="start"
                    frame={startFrame}
                    disabled={disabled}
                    isUploading={isStartUploading}
                    onUpload={onVideoFrameAdd}
                    onRemove={onVideoFrameRemove}
                />
            )}
            {supportsEndFrame && (
                <FrameSlot
                    type="end"
                    frame={endFrame}
                    disabled={disabled}
                    isUploading={isEndUploading}
                    onUpload={onVideoFrameAdd}
                    onRemove={onVideoFrameRemove}
                />
            )}
        </div>
    )
}

export default ChatMediaVideoFrames
