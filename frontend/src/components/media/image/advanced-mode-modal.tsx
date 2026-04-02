import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { toast } from 'sonner'
import { Button } from '../../ui/button'
import { Icon } from '../../ui/icon'
import { mediaService, type ReferenceImageType } from '@/services/media.service'
import { uploadService } from '@/services/upload.service'
import { Shimmer } from '../../ai-elements/shimmer'
import { useTranslation } from 'react-i18next'

export type AdvancedModeData = {
    subject: CategoryData
    scene: CategoryData
    style: CategoryData
}

type Props = {
    open: boolean
    sessionId?: string
    modelName?: string
    provider?: string
    initialData?: AdvancedModeData | null
    onClose: () => void
    onSave: (data: AdvancedModeData) => void | Promise<void>
}

type CategoryKey = 'subject' | 'scene' | 'style'

export type UploadedImage = {
    file?: File
    preview: string
    fileUrl?: string // GCS URL after upload
    fileId?: string // File ID from upload
    isGenerating?: boolean
    isUploading?: boolean
}

export type CategoryData = {
    images: UploadedImage[]
    prompt: string
}

const categories: {
    key: CategoryKey
    icon: string
    titleKey: string
    descriptionKey: string
    sampleImages: string[]
}[] = [
    {
        key: 'subject',
        icon: 'user',
        titleKey: 'media.advancedMode.categories.subject.title',
        descriptionKey: 'media.advancedMode.categories.subject.description',
        sampleImages: [
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/subject-1.png',
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/subject-2.png',
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/subject-3.png'
        ]
    },
    {
        key: 'scene',
        icon: 'scene',
        titleKey: 'media.advancedMode.categories.scene.title',
        descriptionKey: 'media.advancedMode.categories.scene.description',
        sampleImages: [
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/scene-1.png',
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/scene-2.png',
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/scene-3.png'
        ]
    },
    {
        key: 'style',
        icon: 'magic-pen',
        titleKey: 'media.advancedMode.categories.style.title',
        descriptionKey: 'media.advancedMode.categories.style.description',
        sampleImages: [
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/style-1.png',
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/style-2.png',
            'https://storage.googleapis.com/ii-agent-public/generate-media/image/style-3.png'
        ]
    }
]

export const AdvancedModeModal = ({
    open,
    sessionId,
    modelName,
    provider,
    initialData,
    onClose,
    onSave
}: Props) => {
    const { t } = useTranslation()
    const [data, setData] = useState<Record<CategoryKey, CategoryData>>(
        () =>
            initialData || {
                subject: { images: [], prompt: '' },
                scene: { images: [], prompt: '' },
                style: { images: [], prompt: '' }
            }
    )
    const [promptModal, setPromptModal] = useState<{
        open: boolean
        category: CategoryKey | null
        value: string
    }>({ open: false, category: null, value: '' })
    const [saving, setSaving] = useState(false)

    // Sync data when modal opens with initialData
    useEffect(() => {
        if (open && initialData) {
            setData(initialData)
        }
    }, [open, initialData])

    // Handle ESC key to close modal
    useEffect(() => {
        if (!open) return

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose()
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [open, onClose])

    const uploadFileToGCS = async (
        file: File
    ): Promise<{ fileUrl: string; fileId: string } | null> => {
        try {
            // Step 1: Generate upload URL
            const generateUrlResponse = await uploadService.generateUploadUrl({
                file_name: file.name,
                content_type: file.type || 'image/jpeg',
                file_size: file.size
            })

            // Step 2: Upload file to the signed URL
            await new Promise<void>((resolve, reject) => {
                const xhr = new XMLHttpRequest()
                xhr.open('PUT', generateUrlResponse.upload_url, true)
                xhr.setRequestHeader('Content-Type', file.type || 'image/jpeg')

                xhr.onload = function () {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve()
                    } else {
                        reject(
                            new Error(
                                `Failed to upload file: ${xhr.status} ${xhr.statusText}`
                            )
                        )
                    }
                }
                xhr.onerror = function () {
                    reject(
                        new Error('Network error occurred during file upload')
                    )
                }
                xhr.timeout = 300000
                xhr.send(file)
            })

            // Step 3: Call upload complete with session_id
            const completeResponse = await uploadService.uploadComplete({
                id: generateUrlResponse.id,
                file_name: file.name,
                file_size: file.size,
                content_type: file.type || 'image/jpeg',
                session_id: sessionId
            })

            return {
                fileUrl: completeResponse.file_url,
                fileId: generateUrlResponse.id
            }
        } catch (error) {
            console.error('Upload error:', error)
            toast.error(t('imageEdit.errors.uploadFailed'))
            return null
        }
    }

    const handleImageUpload = async (
        category: CategoryKey,
        files: FileList | null
    ) => {
        if (!files) return

        const filesToUpload = Array.from(files)

        for (const file of filesToUpload) {
            const preview = URL.createObjectURL(file)

            // Add image with uploading state
            setData((prev) => ({
                ...prev,
                [category]: {
                    ...prev[category],
                    images: [
                        ...prev[category].images,
                        { file, preview, isUploading: true }
                    ]
                }
            }))

            // Upload to GCS
            const result = await uploadFileToGCS(file)

            if (result) {
                // Update with GCS URL
                setData((prev) => ({
                    ...prev,
                    [category]: {
                        ...prev[category],
                        images: prev[category].images.map((img) =>
                            img.preview === preview
                                ? {
                                      ...img,
                                      fileUrl: result.fileUrl,
                                      fileId: result.fileId,
                                      isUploading: false
                                  }
                                : img
                        )
                    }
                }))
            } else {
                // Remove failed upload
                setData((prev) => ({
                    ...prev,
                    [category]: {
                        ...prev[category],
                        images: prev[category].images.filter(
                            (img) => img.preview !== preview
                        )
                    }
                }))
                URL.revokeObjectURL(preview)
            }
        }
    }

    const handleRemoveImage = (category: CategoryKey, index: number) => {
        setData((prev) => {
            const newImages = [...prev[category].images]
            URL.revokeObjectURL(newImages[index].preview)
            newImages.splice(index, 1)
            return {
                ...prev,
                [category]: {
                    ...prev[category],
                    images: newImages
                }
            }
        })
    }

    const handleClearAll = () => {
        Object.values(data).forEach((cat) => {
            cat.images.forEach((img) => URL.revokeObjectURL(img.preview))
        })
        setData({
            subject: { images: [], prompt: '' },
            scene: { images: [], prompt: '' },
            style: { images: [], prompt: '' }
        })
    }

    const handleSave = async () => {
        try {
            setSaving(true)
            await onSave(data)
            onClose()
        } catch (error) {
            // Errors are handled by the caller (toast/logging)
            console.error('Failed to save advanced mode', error)
        } finally {
            setSaving(false)
        }
    }

    const isProcessing = Object.values(data).some((cat) =>
        cat.images.some((img) => img.isGenerating || img.isUploading)
    )

    const openPromptModal = (category: CategoryKey) => {
        setPromptModal({
            open: true,
            category,
            value: ''
        })
    }

    const handlePromptSubmit = async () => {
        if (!promptModal.category || !promptModal.value.trim()) return

        const category = promptModal.category
        const prompt = promptModal.value.trim()

        // Add placeholder image with generating state
        setData((prev) => ({
            ...prev,
            [category]: {
                ...prev[category],
                images: [
                    ...prev[category].images,
                    { preview: '', isGenerating: true }
                ]
            }
        }))

        // Close prompt modal
        setPromptModal({ open: false, category: null, value: '' })

        try {
            // Use provided model or fallback to default
            const effectiveModelName = modelName
            const effectiveProvider = provider

            const result = await mediaService.generateReferenceImage({
                prompt,
                type: category as ReferenceImageType,
                session_id: sessionId || undefined,
                model_name: effectiveModelName,
                provider: effectiveProvider
            })

            if (result.success && result.url) {
                // Replace generating placeholder with actual image (include file_id if available)
                setData((prev) => {
                    const images = prev[category].images.map((img) =>
                        img.isGenerating
                            ? {
                                  preview: result.url!,
                                  fileUrl: result.url!,
                                  fileId: result.file_id || undefined,
                                  isGenerating: false
                              }
                            : img
                    )
                    return {
                        ...prev,
                        [category]: { ...prev[category], images }
                    }
                })
            } else {
                // Remove generating placeholder on error
                setData((prev) => ({
                    ...prev,
                    [category]: {
                        ...prev[category],
                        images: prev[category].images.filter(
                            (img) => !img.isGenerating
                        )
                    }
                }))
                console.error(
                    'Failed to generate reference image:',
                    result.error
                )
            }
        } catch (error) {
            // Remove generating placeholder on error
            setData((prev) => ({
                ...prev,
                [category]: {
                    ...prev[category],
                    images: prev[category].images.filter(
                        (img) => !img.isGenerating
                    )
                }
            }))
            console.error('Failed to generate reference image:', error)
        }
    }

    if (!open) return null

    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={onClose}
            />
            <div className="relative z-200 bg-white dark:bg-charcoal rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto md:m-4">
                <div className="flex items-center justify-between p-6 pb-4">
                    <h2 className="text-lg font-bold text-charcoal dark:text-white">
                        {t('media.advancedMode.title')}
                    </h2>
                    <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6 rounded-none hover:bg-transparent p-0"
                        onClick={onClose}
                    >
                        <Icon
                            name="close"
                            className="size-6 fill-charcoal dark:fill-white"
                        />
                    </Button>
                </div>

                <div className="p-3 md:p-6 space-y-4">
                    {categories.map((cat) => {
                        const categoryTitle = t(cat.titleKey)
                        const categoryDescription = t(cat.descriptionKey)

                        return (
                            <div
                                key={cat.key}
                                className="flex flex-col md:flex-row items-stretch gap-4"
                            >
                                <div className="w-full md:w-[340px] shrink-0 p-2 md:p-4 rounded-xl bg-blue-gradient flex flex-row md:flex-col items-center">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                            <Icon
                                                name={cat.icon}
                                                className="size-5 text-black fill-black"
                                            />
                                            <span className="font-bold text-black text-sm">
                                                {categoryTitle}
                                            </span>
                                        </div>
                                        <p className="text-xs text-black leading-relaxed md:mb-3">
                                            {categoryDescription}
                                        </p>
                                    </div>
                                    <div className="flex gap-2">
                                        {cat.sampleImages.map((src, idx) => (
                                            <img
                                                key={idx}
                                                src={src}
                                                alt={t(
                                                    'media.advancedMode.sampleAlt',
                                                    {
                                                        title: categoryTitle,
                                                        index: idx + 1
                                                    }
                                                )}
                                                className="w-9 h-10 md:w-[92px] md:h-[103px] rounded-lg object-cover"
                                            />
                                        ))}
                                    </div>
                                </div>

                                <div className="flex-1 flex items-stretch gap-3 bg-sky-blue-3 dark:bg-sky-blue-2/10 rounded-xl p-3">
                                    {data[cat.key].images.map((img, idx) => (
                                        <div
                                            key={idx}
                                            className="relative w-[86px] md:w-[160px] rounded-xl overflow-hidden"
                                        >
                                            {img.isGenerating ||
                                            img.isUploading ? (
                                                <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[#5bc4c4] to-[#3a9a9a]">
                                                    <Shimmer
                                                        className="text-sm font-medium"
                                                        style={{
                                                            backgroundImage:
                                                                'linear-gradient(90deg, #000000 0%, #000000 40%, #ffffff 50%, #000000 60%, #000000 100%)'
                                                        }}
                                                        duration={1}
                                                    >
                                                        {img.isGenerating
                                                            ? t(
                                                                  'media.advancedMode.status.generating'
                                                              )
                                                            : t(
                                                                  'media.advancedMode.status.uploading'
                                                              )}
                                                    </Shimmer>
                                                </div>
                                            ) : (
                                                <>
                                                    <img
                                                        src={img.preview}
                                                        alt={t(
                                                            'media.advancedMode.imageAlt',
                                                            {
                                                                title: t(
                                                                    cat.titleKey
                                                                ),
                                                                index: idx + 1
                                                            }
                                                        )}
                                                        className="w-full h-full object-cover"
                                                    />
                                                    <button
                                                        onClick={() =>
                                                            handleRemoveImage(
                                                                cat.key,
                                                                idx
                                                            )
                                                        }
                                                        className="absolute top-2 right-2 w-6 h-6 rounded-full bg-grey flex items-center justify-center hover:bg-grey-2 transition-colors"
                                                    >
                                                        <Icon
                                                            name="delete"
                                                            className="size-[18px] fill-charcoal"
                                                        />
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    ))}

                                    <div className="w-[86px] md:w-[160px] rounded-xl border border-dashed border-black dark:border-white flex flex-col bg-transparent">
                                        <label className="flex-1 flex flex-col items-center justify-center gap-2 cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-black dark:text-white text-sm py-4">
                                            <input
                                                type="file"
                                                accept="image/*"
                                                className="hidden"
                                                onChange={(e) =>
                                                    handleImageUpload(
                                                        cat.key,
                                                        e.target.files
                                                    )
                                                }
                                            />
                                            <Icon
                                                name="upload"
                                                className="size-5 fill-black dark:fill-white"
                                            />
                                            <span className="hidden md:inline">
                                                {t(
                                                    'media.advancedMode.actions.uploadImage'
                                                )}
                                            </span>
                                        </label>
                                        <div className="border-t border-dashed border-black dark:border-white" />
                                        <button
                                            className="flex-1 flex flex-col items-center justify-center gap-2 cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-black dark:text-white text-sm py-4"
                                            onClick={() =>
                                                openPromptModal(cat.key)
                                            }
                                        >
                                            <Icon
                                                name="prompt"
                                                className="size-5 fill-black dark:fill-white"
                                            />
                                            <span className="hidden md:inline">
                                                {t(
                                                    'media.advancedMode.actions.promptIt'
                                                )}
                                            </span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>

                <div className="flex items-center gap-3 p-6 pt-4">
                    <Button
                        size="lg"
                        className="rounded-xl px-6 bg-charcoal text-sky-blue-2 dark:bg-sky-blue dark:text-black font-bold"
                        onClick={handleSave}
                        disabled={saving || isProcessing}
                    >
                        {saving ? t('common.saving') : t('common.save')}
                    </Button>
                    <Button
                        variant="ghost"
                        size="lg"
                        className="rounded-xl px-6 text-red-2 hover:text-red-2 hover:bg-transparent font-bold"
                        onClick={handleClearAll}
                        disabled={isProcessing}
                    >
                        {t('media.advancedMode.actions.clearAll')}
                    </Button>
                </div>
            </div>

            {promptModal.open && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center">
                    <div
                        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
                        onClick={() =>
                            setPromptModal({
                                open: false,
                                category: null,
                                value: ''
                            })
                        }
                    />
                    <div className="relative bg-white dark:bg-[#1a2a30] rounded-2xl shadow-2xl w-full max-w-md border border-[#d7dde2] dark:border-[#2a3a40] m-4">
                        <div className="flex items-center justify-between p-4 border-b border-[#d7dde2] dark:border-[#2a3a40]">
                            <h3 className="text-base font-semibold text-[#0b1218] dark:text-white">
                                {t(
                                    'media.advancedMode.actions.generateReferences'
                                )}
                            </h3>
                            <Button
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7 rounded-full hover:bg-black/10 dark:hover:bg-white/10"
                                onClick={() =>
                                    setPromptModal({
                                        open: false,
                                        category: null,
                                        value: ''
                                    })
                                }
                            >
                                <Icon
                                    name="close"
                                    className="size-4 fill-[#0b1218] dark:fill-white"
                                />
                            </Button>
                        </div>
                        <div className="p-4">
                            <textarea
                                className="w-full h-32 bg-[#f4f6f8] dark:bg-[#263535] rounded-xl p-3 text-sm text-[#0b1218] dark:text-white placeholder-grey-1 border-none outline-none resize-none"
                                placeholder={t(
                                    'media.advancedMode.promptPlaceholder'
                                )}
                                value={promptModal.value}
                                onChange={(e) =>
                                    setPromptModal((prev) => ({
                                        ...prev,
                                        value: e.target.value
                                    }))
                                }
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault()
                                        handlePromptSubmit()
                                    }
                                }}
                                autoFocus
                            />
                        </div>
                        <div className="p-4 pt-0">
                            <Button
                                size="sm"
                                className="rounded-full px-6 bg-[#263533] text-[#a6ffff] hover:bg-[#a6ffff] hover:text-[#212121] transition-colors"
                                onClick={handlePromptSubmit}
                            >
                                {t('media.advancedMode.actions.makeIt')}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>,
        document.body
    )
}
