import { useRef, useState, useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Icon } from '../../ui/icon'
import type { VideoFrameReference } from '@/typings/agent'
import { Loader2 } from 'lucide-react'

// Array-based interface for managing multiple frames
interface VideoFrameUploadProps {
    frames: VideoFrameReference[]
    supportsStartFrame?: boolean
    supportsEndFrame?: boolean
    onFrameAdd: (file: File, type: 'start' | 'end') => void
    disabled?: boolean
    uploadingFrameIds?: Set<'start' | 'end'>
}

// Simple single-frame interface for VideoInputLayout usage
interface SingleFrameUploadProps {
    label: string
    file?: File | null
    previewUrl?: string | null
    onFileChange: (file: File | null) => void
    disabled?: boolean
}

interface FrameUploadButtonProps {
    type: 'start' | 'end'
    hasFrame: boolean
    onUpload: (file: File) => void
    disabled?: boolean
    isUploading?: boolean
}

const FrameUploadButton = ({
    type,
    hasFrame,
    onUpload,
    disabled,
    isUploading
}: FrameUploadButtonProps) => {
    const inputRef = useRef<HTMLInputElement>(null)

    const handleClick = () => {
        if (!disabled && !isUploading && inputRef.current) {
            inputRef.current.click()
        }
    }

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) {
            onUpload(file)
            // Reset input for re-upload
            if (inputRef.current) {
                inputRef.current.value = ''
            }
        }
    }

    const label = type === 'start' ? 'Start frame' : 'End frame'

    return (
        <div className="relative">
            <input
                ref={inputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.gif,.webp,.bmp,.heic,.heif"
                onChange={handleFileChange}
                className="hidden"
                disabled={disabled || isUploading}
            />

            <button
                type="button"
                onClick={handleClick}
                disabled={disabled || isUploading}
                className={cn(
                    'h-7 px-3 rounded-full',
                    'border border-dashed',
                    hasFrame || isUploading
                        ? 'border-firefly dark:border-sky-blue bg-firefly/10 dark:bg-sky-blue/10 text-black dark:text-sky-blue'
                        : 'border-black/50 dark:border-white/50 text-black/70 dark:text-white/70',
                    'flex items-center gap-1.5',
                    'hover:border-sky-blue hover:bg-sky-blue/5 transition-colors',
                    'cursor-pointer text-xs',
                    (disabled || isUploading) && 'opacity-50 cursor-not-allowed'
                )}
            >
                {isUploading ? (
                    <Loader2 className="size-3 text-sky-blue animate-spin" />
                ) : hasFrame ? (
                    <Icon name="check" className="size-3 fill-sky-blue" />
                ) : (
                    <svg
                        width="12"
                        height="12"
                        viewBox="0 0 20 20"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                    >
                        <path
                            d="M10 4V16M4 10H16"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        />
                    </svg>
                )}
                <span className="font-medium">{label}</span>
            </button>
        </div>
    )
}

/**
 * SingleFrameUpload - Simple single-frame upload component
 * Used by VideoInputLayout for start/end frame uploads
 * Matches Figma design: 104x61px dashed border box with + icon
 */
export const SingleFrameUpload = ({
    label,
    file,
    previewUrl,
    onFileChange,
    disabled
}: SingleFrameUploadProps) => {
    const inputRef = useRef<HTMLInputElement>(null)
    const [localPreview, setLocalPreview] = useState<string | null>(null)
    const [previewError, setPreviewError] = useState(false)

    // Generate preview URL from File object
    useEffect(() => {
        if (file) {
            const url = URL.createObjectURL(file)
            setLocalPreview(url)
            return () => URL.revokeObjectURL(url)
        } else {
            setLocalPreview(null)
        }
    }, [file])

    const displayUrl = previewUrl || localPreview

    const handleClick = () => {
        if (!disabled && inputRef.current) {
            inputRef.current.click()
        }
    }

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0]
        if (selectedFile) {
            onFileChange(selectedFile)
            // Reset input for re-upload
            if (inputRef.current) {
                inputRef.current.value = ''
            }
        }
    }

    const handleRemove = (e: React.MouseEvent) => {
        e.stopPropagation()
        onFileChange(null)
    }

    return (
        <div className="relative">
            <input
                ref={inputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.gif,.webp,.bmp,.heic,.heif"
                onChange={handleFileChange}
                className="hidden"
                disabled={disabled}
            />

            {displayUrl && !previewError ? (
                // Show uploaded frame preview
                <div className="relative">
                    <div
                        className={cn(
                            'w-[104px] h-[61px] rounded-[12px] overflow-hidden',
                            'border border-dashed border-white'
                        )}
                    >
                        <img
                            src={displayUrl}
                            alt={label}
                            className="w-full h-full object-cover"
                            onError={() => setPreviewError(true)}
                        />
                    </div>
                    {/* Close button */}
                    <button
                        type="button"
                        onClick={handleRemove}
                        disabled={disabled}
                        className={cn(
                            'absolute -top-1.5 -right-1.5',
                            'w-[16px] h-[16px] rounded-full',
                            'bg-[#ff3b30] flex items-center justify-center',
                            'hover:bg-[#ff3b30]/80 transition-colors',
                            disabled && 'opacity-50 cursor-not-allowed'
                        )}
                    >
                        <Icon name="close" className="size-2 fill-white" />
                    </button>
                </div>
            ) : (
                // Empty slot - upload button matching Figma design
                <button
                    type="button"
                    onClick={handleClick}
                    disabled={disabled}
                    className={cn(
                        'w-[104px] h-[61px] rounded-[12px]',
                        'border border-dashed border-white',
                        'flex flex-col items-center justify-center gap-1',
                        'bg-transparent',
                        'hover:border-[#a6ffff] hover:bg-[#a6ffff]/5 transition-colors',
                        'cursor-pointer',
                        disabled && 'opacity-50 cursor-not-allowed'
                    )}
                >
                    {/* Plus icon */}
                    <svg
                        width="20"
                        height="20"
                        viewBox="0 0 20 20"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                    >
                        <path
                            d="M10 4V16M4 10H16"
                            stroke="white"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        />
                    </svg>
                    <span className="font-['Satoshi',sans-serif] font-normal text-[14px] text-white">
                        {label}
                    </span>
                </button>
            )}
        </div>
    )
}

export const VideoFrameUpload = ({
    frames,
    supportsStartFrame = true,
    supportsEndFrame = true,
    onFrameAdd,
    disabled,
    uploadingFrameIds
}: VideoFrameUploadProps) => {
    const startFrame = useMemo(
        () => frames.find((f) => f.type === 'start'),
        [frames]
    )

    const endFrame = useMemo(
        () => frames.find((f) => f.type === 'end'),
        [frames]
    )

    // Check if a frame of each type is currently uploading
    const isStartUploading = uploadingFrameIds?.has('start') ?? false
    const isEndUploading = uploadingFrameIds?.has('end') ?? false

    if (!supportsStartFrame && !supportsEndFrame) {
        return null
    }

    return (
        <div className="flex items-center gap-2">
            {supportsStartFrame && (
                <FrameUploadButton
                    type="start"
                    hasFrame={!!startFrame}
                    onUpload={(file) => onFrameAdd(file, 'start')}
                    disabled={disabled}
                    isUploading={isStartUploading}
                />
            )}
            {supportsEndFrame && (
                <FrameUploadButton
                    type="end"
                    hasFrame={!!endFrame}
                    onUpload={(file) => onFrameAdd(file, 'end')}
                    disabled={disabled}
                    isUploading={isEndUploading}
                />
            )}
        </div>
    )
}

export default VideoFrameUpload
