import { useState } from 'react'
import { Folder, Loader2 } from 'lucide-react'
import { Icon } from './ui/icon'
import { getFileIconAndColor } from '@/utils/file-utils'
import type { FileUploadStatus } from '@/hooks/use-upload-files'
import { useTranslation } from 'react-i18next'

/** Tiny wrapper so each thumbnail can track its own load-error state. */
const ImagePreviewItem = ({
    file,
    isUploading,
    onRemove
}: {
    file: FileUploadStatus
    isUploading: boolean
    onRemove: (fileName: string) => void
}) => {
    const [loadError, setLoadError] = useState(false)

    if (loadError) {
        const { IconComponent, bgColor, label } = getFileIconAndColor(file.name)
        return (
            <div className="relative flex items-center gap-2 dark:bg-grey text-white rounded-lg p-2 pr-7">
                <div
                    className={`flex items-center justify-center w-10 h-10 ${bgColor} rounded-full`}
                >
                    <IconComponent className="size-5 text-white" />
                </div>
                <div className="flex flex-col text-black">
                    <span className="text-xs font-semibold truncate max-w-[145px]">
                        {file.name}
                    </span>
                    <span className="text-xs">{label}</span>
                </div>
                <button
                    onClick={() => onRemove(file.name)}
                    className="absolute right-1 top-1 cursor-pointer"
                >
                    <Icon name="close-circle" className="size-4 fill-black" />
                </button>
            </div>
        )
    }

    return (
        <div className="relative">
            <div className="size-12 rounded-lg overflow-hidden">
                <img
                    src={file.preview}
                    alt={file.name}
                    className="w-full h-full object-cover"
                    onError={() => setLoadError(true)}
                />
            </div>
            {(isUploading || file.loading) && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-xl">
                    <Loader2 className="size-5 text-black animate-spin" />
                </div>
            )}
            <button
                onClick={() => onRemove(file.name)}
                className="absolute right-1 top-1 cursor-pointer border-[0.5px] border-white rounded-full bg-white"
            >
                <Icon name="close-circle" className="size-4 fill-black" />
            </button>
        </div>
    )
}

interface FilesPreviewProps {
    files: FileUploadStatus[]
    isUploading: boolean
    className?: string
    onRemove: (fileName: string) => void
}

const FilesPreview = ({
    files,
    isUploading,
    className = '',
    onRemove
}: FilesPreviewProps) => {
    const { t } = useTranslation()
    if (files.length === 0) return null

    return (
        <div
            className={`absolute top-4 left-4 right-2 flex items-center overflow-auto gap-2 z-[23] ${className}`}
        >
            {files.map((file) => {
                if (file.isImage && file.preview) {
                    return (
                        <ImagePreviewItem
                            key={file.id ?? file.name}
                            file={file}
                            isUploading={isUploading}
                            onRemove={onRemove}
                        />
                    )
                }

                if (file.isFolder) {
                    return (
                        <div
                            key={file.id ?? file.name}
                            className="relative flex items-center gap-2 dark:bg-grey bg-white text-black rounded-lg px-3 py-2 pr-8 border border-grey dark:border-grey-4 shadow-sm"
                        >
                            <div className="flex items-center justify-center w-8 h-8 bg-firefly dark:bg-sky-blue rounded-full">
                                {isUploading || file.loading ? (
                                    <Loader2 className="size-4 animate-spin" />
                                ) : (
                                    <Folder className="size-4" />
                                )}
                            </div>
                            <div className="flex flex-col">
                                <span className="text-xs font-semibold truncate max-w-[145px]">
                                    {file.name}
                                </span>
                                <span className="text-xs">
                                    {file.fileCount
                                        ? t('uploads.fileCount', {
                                              count: file.fileCount
                                          })
                                        : t('uploads.folder')}
                                </span>
                            </div>
                            <button
                                onClick={() => onRemove(file.name)}
                                className="absolute right-1 top-1 cursor-pointer"
                            >
                                <Icon
                                    name="close-circle"
                                    className="size-4 fill-black"
                                />
                            </button>
                        </div>
                    )
                }

                const { label } = getFileIconAndColor(file.name)
                return (
                    <div
                        key={file.id ?? file.name}
                        className="relative flex items-center gap-2 dark:bg-grey text-white rounded-lg p-2 pr-7"
                    >
                        {(isUploading || file.loading) && (
                            <div
                                className={`flex items-center justify-center w-10 h-10 rounded-full`}
                            >
                                <Loader2 className="size-5 text-black animate-spin" />
                            </div>
                        )}
                        <div className="flex flex-col text-black">
                            <span className="text-xs font-semibold truncate max-w-[145px]">
                                {file.name}
                            </span>
                            <span className="text-xs">{label}</span>
                        </div>
                        <button
                            onClick={() => onRemove(file.name)}
                            className="absolute right-1 top-1 cursor-pointer"
                        >
                            <Icon
                                name="close-circle"
                                className="size-4 fill-black"
                            />
                        </button>
                    </div>
                )
            })}
        </div>
    )
}

export default FilesPreview
