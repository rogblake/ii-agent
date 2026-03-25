import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { chatService } from '@/services/chat.service'
import { getFileIconAndColor } from '@/utils/file-utils'

interface FileData {
    id: string
    file_name: string
    file_size: number
    content_type: string
    created_at: string
}

interface ImageFileItemProps {
    file: FileData
    name: string
    sessionId: string
    isShareMode: boolean
    fileContent?: string
    onPreview: (url: string, name: string) => void
}

const ImageFileItem = ({
    file,
    name,
    sessionId,
    isShareMode,
    fileContent,
    onPreview
}: ImageFileItemProps) => {
    const { t } = useTranslation()
    // HEIC files must always be fetched through the backend API which
    // converts to JPEG.  The fileContent prop holds the raw GCS URL that
    // browsers cannot render.
    const isHeic = /\.(heic|heif)$/i.test(name)
    const usableContent = isHeic ? null : (fileContent ?? null)

    const [imageUrl, setImageUrl] = useState<string | null>(usableContent)
    const [isLoading, setIsLoading] = useState(!usableContent)
    const [loadError, setLoadError] = useState(false)
    const fetchedRef = useRef(false)

    useEffect(() => {
        // If we already have usable content from props, no need to fetch
        if (usableContent) {
            setImageUrl(usableContent)
            setIsLoading(false)
            return
        }

        // Prevent duplicate fetches
        if (fetchedRef.current) return
        fetchedRef.current = true

        let blobUrl: string | null = null

        const fetchImage = async () => {
            try {
                const blob = isShareMode
                    ? await chatService.getPublicFileContent({
                          fileId: file.id,
                          sessionId
                      })
                    : await chatService.getFileContent({
                          fileId: file.id
                      })

                blobUrl = URL.createObjectURL(blob)
                setImageUrl(blobUrl)
            } catch (error) {
                console.error(`Error fetching image ${file.file_name}:`, error)
            } finally {
                setIsLoading(false)
            }
        }

        fetchImage()

        return () => {
            if (blobUrl) {
                URL.revokeObjectURL(blobUrl)
            }
        }
    }, [file.id, file.file_name, sessionId, isShareMode, fileContent])

    if (isLoading) {
        return (
            <div className="inline-block rounded-xl overflow-hidden max-w-[320px]">
                <div className="w-40 h-40 rounded-xl overflow-hidden bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                    <span className="text-gray-500 text-sm">
                        {t('common.loading')}
                    </span>
                </div>
            </div>
        )
    }

    if (imageUrl && !loadError) {
        return (
            <div
                className="inline-block rounded-xl overflow-hidden max-w-[320px] cursor-pointer"
                onClick={() => onPreview(imageUrl, name)}
            >
                <div className="w-40 h-40 rounded-xl overflow-hidden hover:opacity-80 transition-opacity">
                    <img
                        src={imageUrl}
                        alt={name}
                        className="w-full h-full object-cover"
                        loading="lazy"
                        onError={() => setLoadError(true)}
                    />
                </div>
            </div>
        )
    }

    // Fallback to file icon if image failed to load
    const { IconComponent, bgColor, label } = getFileIconAndColor(name)

    return (
        <div className="inline-block bg-[#35363a] text-white rounded-2xl px-4 py-3 border border-gray-700 shadow-sm max-w-fit">
            <div className="flex items-center gap-3">
                <div
                    className={`flex items-center justify-center w-12 h-12 ${bgColor} rounded-xl`}
                >
                    <IconComponent className="size-6 text-white" />
                </div>
                <div className="flex flex-col">
                    <span className="text-base font-medium">{name}</span>
                    <span className="text-left text-sm text-gray-500">
                        {label}
                    </span>
                </div>
            </div>
        </div>
    )
}

interface UploadedFilesDisplayProps {
    files?: Array<FileData>
    fileContents?: Record<string, string>
    sessionId?: string
    isShareMode?: boolean
}

export const UploadedFilesDisplay = ({
    files,
    fileContents,
    sessionId,
    isShareMode = false
}: UploadedFilesDisplayProps) => {
    const { t } = useTranslation()
    const [previewImage, setPreviewImage] = useState<{
        url: string
        name: string
    } | null>(null)

    if (!files || files.length === 0) return null

    const folderPattern = /^(.+?)\s*\((\d+)\s*files?\)$/
    const folders: Array<{
        file: FileData
        name: string
        count: number
        index: number
    }> = []
    const regularFiles: Array<{
        file: FileData
        name: string
        index: number
    }> = []

    files.forEach((file, index) => {
        const match = file.file_name.match(folderPattern)
        if (match) {
            folders.push({
                file,
                name: match[1],
                count: parseInt(match[2]),
                index
            })
        } else {
            regularFiles.push({ file, name: file.file_name, index })
        }
    })

    const handlePreview = (url: string, name: string) => {
        setPreviewImage({ url, name })
    }

    return (
        <div className="flex flex-row justify-end flex-wrap gap-2 mb-2">
            {folders.map(({ name, count, index }) => (
                <div
                    key={`folder-${index}`}
                    className="inline-block bg-[#35363a] text-white rounded-2xl px-4 py-3 border border-gray-700 shadow-sm max-w-fit"
                >
                    <div className="flex items-center gap-3">
                        <div className="flex items-center justify-center w-12 h-12 bg-blue-600 rounded-xl">
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="24"
                                height="24"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                className="size-6 text-white"
                            >
                                <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
                            </svg>
                        </div>
                        <div className="flex flex-col">
                            <span className="text-base font-medium">
                                {name}
                            </span>
                            <span className="text-left text-sm text-gray-500">
                                {t('uploads.fileCount', { count })}
                            </span>
                        </div>
                    </div>
                </div>
            ))}
            {regularFiles.map(({ file, name, index }) => {
                const isImage = /\.(jpeg|jpg|gif|png|webp|svg|heic|bmp)$/i.test(
                    name
                )

                if (isImage && sessionId) {
                    return (
                        <ImageFileItem
                            key={`file-${index}`}
                            file={file}
                            name={name}
                            sessionId={sessionId}
                            isShareMode={isShareMode}
                            fileContent={fileContents?.[name]}
                            onPreview={handlePreview}
                        />
                    )
                }

                const { IconComponent, bgColor, label } =
                    getFileIconAndColor(name)

                return (
                    <div
                        key={`file-${index}`}
                        className="inline-block bg-[#35363a] text-white rounded-2xl px-4 py-3 border border-gray-700 shadow-sm max-w-fit"
                    >
                        <div className="flex items-center gap-3">
                            <div
                                className={`flex items-center justify-center w-12 h-12 ${bgColor} rounded-xl`}
                            >
                                <IconComponent className="size-6 text-white" />
                            </div>
                            <div className="flex flex-col">
                                <span className="text-base font-medium">
                                    {name}
                                </span>
                                <span className="text-left text-sm text-gray-500">
                                    {label}
                                </span>
                            </div>
                        </div>
                    </div>
                )
            })}
            {previewImage && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
                    onClick={() => setPreviewImage(null)}
                >
                    <div className="relative max-w-[90vw] max-h-[90vh]">
                        <button
                            className="absolute -top-10 right-0 text-white hover:text-gray-300 transition-colors"
                            onClick={() => setPreviewImage(null)}
                        >
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="24"
                                height="24"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            >
                                <line x1="18" y1="6" x2="6" y2="18" />
                                <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                        </button>
                        <img
                            src={previewImage.url}
                            alt={previewImage.name}
                            className="max-w-full max-h-[90vh] object-contain rounded-lg"
                            onClick={(e) => e.stopPropagation()}
                        />
                        <div className="absolute -bottom-10 left-0 text-white text-sm">
                            {previewImage.name}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
