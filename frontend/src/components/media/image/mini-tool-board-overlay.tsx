import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
    addUploadedFiles,
    selectChatMediaPreference,
    selectCurrentMessageFileIds,
    selectUploadedFiles,
    setChatMediaPreference,
    setCurrentMessageFileIds,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { toast } from 'sonner'
import { Button } from '../../ui/button'
import { Icon } from '../../ui/icon'
import { type MiniTool } from '@/constants/media-tools'
import { uploadService } from '@/services/upload.service'
import { type MediaLibraryItem } from '@/typings/upload'
import { mediaToolsService } from '@/services/media-tools.service'
import { useUploadFiles } from '@/hooks/use-upload-files'
import clsx from 'clsx'

type Props = {
    open: boolean
    selectedTool?: {
        id: string
        name: string
        sample_set_id?: string
    } | null
    toolDetail?: MiniTool | null
    sessionId?: string
    onClose: () => void
    onClear?: () => void
}

const INITIAL_LIBRARY_LIMIT = 12
const BROWSE_MORE_LIMIT = 50

const MiniToolBoardOverlay = ({
    open,
    selectedTool,
    toolDetail,
    sessionId,
    onClose,
    onClear
}: Props) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)
    const uploadedFiles = useAppSelector(selectUploadedFiles)
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const { uploadFileWithSignedUrl } = useUploadFiles()

    const [resolvedTool, setResolvedTool] = useState<MiniTool | null>(
        toolDetail ?? null
    )
    const [libraryItems, setLibraryItems] = useState<MediaLibraryItem[]>([])
    const [libraryPageSize, setLibraryPageSize] = useState(
        INITIAL_LIBRARY_LIMIT
    )
    const libraryPageSizeRef = useRef(INITIAL_LIBRARY_LIMIT)
    const [libraryLoading, setLibraryLoading] = useState(false)
    const [uploading, setUploading] = useState(false)
    const [selectedMediaIds, setSelectedMediaIds] = useState<string[]>([])
    const [myLibraryOpen, setMyLibraryOpen] = useState(false)
    const [userMediaItems, setUserMediaItems] = useState<MediaLibraryItem[]>([])
    const [userMediaLoading, setUserMediaLoading] = useState(false)
    const fileInputRef = useRef<HTMLInputElement | null>(null)
    const boardRef = useRef<HTMLDivElement | null>(null)
    const myLibraryRef = useRef<HTMLDivElement | null>(null)

    const activeTool = useMemo<MiniTool | null>(() => {
        if (resolvedTool) return resolvedTool
        if (selectedTool) {
            return {
                id: selectedTool.id,
                name: selectedTool.name,
                description: '',
                sample_set_id: selectedTool.sample_set_id,
                min_images: 1,
                max_images: 1
            }
        }
        return null
    }, [resolvedTool, selectedTool])

    const previewTool = useMemo<MiniTool | null>(() => {
        if (activeTool) return activeTool
        if (selectedTool) {
            return {
                id: selectedTool.id,
                name: selectedTool.name,
                description: '',
                sample_set_id: selectedTool.sample_set_id,
                min_images: 1,
                max_images: 1
            }
        }
        return null
    }, [activeTool, selectedTool])

    useEffect(() => {
        libraryPageSizeRef.current = libraryPageSize
    }, [libraryPageSize])

    useEffect(() => {
        if (toolDetail && selectedTool?.id === toolDetail.id) {
            setResolvedTool(toolDetail)
        } else if (
            !selectedTool ||
            !toolDetail ||
            toolDetail.id !== selectedTool?.id
        ) {
            setResolvedTool(null)
        }
    }, [toolDetail, selectedTool?.id])

    useEffect(() => {
        if (!open || resolvedTool || !selectedTool?.id) return

        let mounted = true
        mediaToolsService
            .listMediaTools()
            .then((tools) => {
                if (!mounted) return
                const detail =
                    tools.find((tool) => tool.id === selectedTool.id) || null
                setResolvedTool(detail)
            })
            .catch((err) => {
                console.error('Failed to load mini tool detail', err)
            })

        return () => {
            mounted = false
        }
    }, [open, resolvedTool, selectedTool?.id])

    useEffect(() => {
        if (!open) {
            setSelectedMediaIds([])
            setLibraryItems([])
            setUserMediaItems([])
            setLibraryPageSize(INITIAL_LIBRARY_LIMIT)
            setMyLibraryOpen(false)
            return
        }

        // Load selected media IDs from currentMessageFileIds (source of truth for attached files)
        // instead of reference_file_ids to avoid conflicts when user changes attachments
        setSelectedMediaIds(currentMessageFileIds)
    }, [open, currentMessageFileIds, selectedTool?.id])

    useEffect(() => {
        if (!open) return

        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target as Node
            const insideBoard = boardRef.current?.contains(target)
            const insideLibrary = myLibraryRef.current?.contains(target)
            if (!insideBoard && !insideLibrary) {
                setMyLibraryOpen(false)
                onClose()
            }
        }

        document.addEventListener('mousedown', handleClickOutside)

        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
        }
    }, [open, onClose])

    const renderPreview = (tool: MiniTool) => {
        if (tool.preview) {
            return (
                <img
                    src={tool.preview}
                    alt={tool.name}
                    className="h-full w-full rounded-[12px] object-cover"
                />
            )
        }

        return (
            <div className="flex h-full w-full items-center justify-center">
                <div className="flex w-[90%] items-center justify-between gap-3">
                    <div className="relative h-[85px] w-[72px] rounded-lg bg-gradient-to-br from-[#dcdfe5] via-white to-[#c7ccd4] dark:from-[#1f2b34] dark:via-[#0f1f26] dark:to-[#24323c]">
                        <span className="absolute inset-x-0 bottom-2 text-center text-[10px] font-semibold text-[#212121] dark:text-white">
                            {t('media.miniTools.before')}
                        </span>
                    </div>
                    <span className="text-lg text-[#6b7280] dark:text-grey-1">
                        →
                    </span>
                    <div className="relative h-[85px] w-[72px] rounded-lg bg-gradient-to-br from-[#dfeafc] via-white to-[#bad8ff] dark:from-[#1d2f3d] dark:via-[#0f1f26] dark:to-[#1f3d52]">
                        <span className="absolute inset-x-0 bottom-2 text-center text-[10px] font-semibold text-[#212121] dark:text-white">
                            {t('media.miniTools.after')}
                        </span>
                    </div>
                </div>
            </div>
        )
    }

    const ensureMediaInStore = useCallback(
        (item: MediaLibraryItem) => {
            const exists = uploadedFiles.some((file) => file.id === item.id)
            if (exists) return

            dispatch(
                addUploadedFiles([
                    {
                        id: item.id,
                        name:
                            item.name ||
                            t('media.miniToolBoard.selectedImageName'),
                        path: item.url,
                        size: 0
                    }
                ])
            )
        },
        [dispatch, t, uploadedFiles]
    )

    const fetchLibrary = useCallback(async (pageSize: number) => {
        setLibraryLoading(true)
        try {
            const response = await uploadService.getUserMediaLibrary({
                limit: pageSize,
                offset: 0
            })
            setLibraryItems(response.items)
            setLibraryPageSize(pageSize)
            if (pageSize > INITIAL_LIBRARY_LIMIT) {
                setUserMediaItems(response.items.slice(INITIAL_LIBRARY_LIMIT))
            } else {
                setUserMediaItems([])
            }
        } finally {
            setLibraryLoading(false)
        }
    }, [])

    const refreshLibrary = useCallback(async () => {
        try {
            await fetchLibrary(libraryPageSizeRef.current)
        } catch (err) {
            console.error('Failed to load media library', err)
        }
    }, [fetchLibrary])

    const loadUserMediaLibrary = useCallback(async () => {
        setUserMediaLoading(true)
        try {
            await fetchLibrary(BROWSE_MORE_LIMIT)
        } catch (err) {
            console.error('Failed to load user media library', err)
        } finally {
            setUserMediaLoading(false)
        }
    }, [fetchLibrary])

    useEffect(() => {
        if (!open || !activeTool) return
        void refreshLibrary()
    }, [open, activeTool, refreshLibrary])

    useEffect(() => {
        if (!myLibraryOpen) return
        setUserMediaItems(libraryItems.slice(INITIAL_LIBRARY_LIMIT))
    }, [libraryItems, myLibraryOpen])

    const handleToggleBrowseMore = useCallback(() => {
        if (myLibraryOpen) {
            setMyLibraryOpen(false)
            return
        }
        setMyLibraryOpen(true)
        void loadUserMediaLibrary()
    }, [loadUserMediaLibrary, myLibraryOpen])

    const handleUploadClick = () => {
        fileInputRef.current?.click()
    }

    const handleFileChange = async (
        event: React.ChangeEvent<HTMLInputElement>
    ) => {
        const file = event.target.files?.[0]
        if (!file) return

        setUploading(true)
        try {
            const uploadResult = await uploadFileWithSignedUrl(file, sessionId)
            if (!uploadResult) {
                toast.error(t('media.miniToolBoard.uploadError'))
                return
            }

            const { fileId, fileUrl } = uploadResult
            const alreadyStored = uploadedFiles.some(
                (stored) => stored.id === fileId
            )
            if (!alreadyStored) {
                dispatch(
                    addUploadedFiles([
                        {
                            id: fileId,
                            name: file.name,
                            path: fileUrl,
                            size: file.size
                        }
                    ])
                )
            }

            await refreshLibrary()
            const { maxImages } = getImageLimits()
            setSelectedMediaIds((prev) => {
                if (prev.includes(fileId)) return prev
                if (prev.length >= maxImages) {
                    return [...prev.slice(1), fileId]
                }
                return [...prev, fileId]
            })
        } catch (err) {
            console.error('Upload failed', err)
            toast.error(t('media.miniToolBoard.uploadError'))
        } finally {
            setUploading(false)
            if (fileInputRef.current) {
                fileInputRef.current.value = ''
            }
        }
    }

    const getImageLimits = useCallback(() => {
        const minImages = activeTool?.min_images ?? 1
        const maxImages = activeTool?.max_images ?? 1
        return { minImages, maxImages }
    }, [activeTool])

    const handleSelectMedia = (item: MediaLibraryItem) => {
        if (item.id.startsWith('placeholder')) return
        const { maxImages } = getImageLimits()
        setSelectedMediaIds((prev) => {
            if (prev.includes(item.id)) {
                return prev.filter((id) => id !== item.id)
            }
            if (prev.length >= maxImages) {
                return [...prev.slice(1), item.id]
            }
            return [...prev, item.id]
        })
        ensureMediaInStore(item)
    }

    const handleSelectFromMyLibrary = (item: MediaLibraryItem) => {
        const { maxImages } = getImageLimits()
        setSelectedMediaIds((prev) => {
            if (prev.includes(item.id)) {
                return prev.filter((id) => id !== item.id)
            }
            if (prev.length >= maxImages) {
                return [...prev.slice(1), item.id]
            }
            return [...prev, item.id]
        })
        ensureMediaInStore(item)
        if (getImageLimits().maxImages === 1) {
            setMyLibraryOpen(false)
        }
    }

    const handleConfirmSelection = () => {
        const { minImages } = getImageLimits()

        // Validate minimum image requirement
        if (selectedMediaIds.length < minImages) {
            toast.error(
                minImages === 1
                    ? t('media.miniToolBoard.selectAtLeastOne')
                    : t('media.miniToolBoard.selectAtLeastCount', {
                          count: minImages
                      })
            )
            return
        }

        setMyLibraryOpen(false)
        onClose()

        if (selectedMediaIds.length > 0 && activeTool) {
            const confirmedIds: string[] = []
            for (const mediaId of selectedMediaIds) {
                const selectedItem =
                    libraryItems.find((item) => item.id === mediaId) ||
                    userMediaItems.find((item) => item.id === mediaId)

                if (selectedItem) {
                    ensureMediaInStore(selectedItem)
                    confirmedIds.push(selectedItem.id)
                }
            }

            // Set preference with mini_tools data
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    enabled: true,
                    type: 'image',
                    mini_tools: {
                        ...chatMediaPreference.mini_tools,
                        id: activeTool.id,
                        name: activeTool.name,
                        reference_file_ids: confirmedIds
                    }
                })
            )

            // Replace currentMessageFileIds with selected files (don't add, replace to avoid duplicates)
            dispatch(setCurrentMessageFileIds(confirmedIds))
        }

        requestAnimationFrame(() => {
            setSelectedMediaIds([])
        })
    }

    if (!open || !selectedTool || !activeTool) return null

    const selectedName = activeTool.name

    return (
        <div
            className="fixed inset-0 z-40 flex items-end md:items-center justify-center bg-grey/[0.87] dark:bg-firefly/[0.87] md:px-4 transition-opacity duration-200"
            onClick={(e) => {
                if (e.target === e.currentTarget) {
                    onClose()
                }
            }}
        >
            <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-stretch sm:gap-0 transition-all duration-200">
                <div
                    ref={boardRef}
                    className={clsx(
                        'flex flex-col w-full md:max-w-[90vw] sm:w-[420px] sm:max-w-[420px] max-h-[85vh] rounded-xl bg-white p-5 text-[#0b1419] backdrop-blur-sm dark:bg-[#181E1C] dark:text-white transition-all duration-200 sm:h-[85vh]',
                        myLibraryOpen && 'rounded-r-none'
                    )}
                >
                    <div className="overflow-y-auto flex-1">
                        <div className="relative mb-4 flex items-center justify-center">
                            {!myLibraryOpen && (
                                <Button
                                    size="icon"
                                    variant="ghost"
                                    className="absolute right-0 top-0"
                                    onClick={onClear}
                                    title={t('media.miniTools.clear')}
                                >
                                    <Icon name="close-2" className="size-6" />
                                </Button>
                            )}
                        </div>

                        <div className="flex justify-center">
                            <div className="w-[210px] rounded-[12px]">
                                <div className="relative aspect-[170/126] w-full overflow-hidden rounded-[12px]">
                                    {previewTool && renderPreview(previewTool)}
                                </div>
                            </div>
                        </div>
                        <div className="px-10 mb-4 text-sm font-semibold text-center truncate">
                            {selectedName}
                        </div>

                        <div className="flex flex-col items-center gap-2">
                            <Button
                                type="button"
                                disabled={uploading}
                                onClick={handleUploadClick}
                                className="h-[42px] flex items-center justify-center gap-2 rounded-[12px] border border-black dark:border-[#BEE6F0] px-4 py-3 text-[16px] font-semibold text-[#181E1C] transition hover:bg-[#e9f6fa] disabled:cursor-not-allowed disabled:opacity-60 dark:text-[#BEE6F0] dark:hover:bg-white/5"
                            >
                                {uploading
                                    ? t('media.miniToolBoard.uploading')
                                    : t('media.miniToolBoard.uploadToStart')}
                            </Button>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={handleFileChange}
                            />
                        </div>

                        <p className="mt-6 text-center text-xs text-black dark:text-white/80">
                            {t('media.miniToolBoard.pickFromLibrary')}
                        </p>
                        {libraryLoading && (
                            <p className="mt-1 text-center text-[11px] text-black dark:text-grey-1">
                                {t('media.miniToolBoard.loadingLibrary')}
                            </p>
                        )}

                        <div className="mt-3 grid grid-cols-4 gap-2">
                            {Array.from({ length: INITIAL_LIBRARY_LIMIT }).map(
                                (_, index) => {
                                    const item = libraryItems[index]
                                    const hasImage = !!item?.url
                                    return (
                                        <button
                                            key={item?.id || `slot-${index}`}
                                            type="button"
                                            onClick={() => {
                                                if (hasImage && item) {
                                                    handleSelectMedia(item)
                                                }
                                            }}
                                            disabled={!hasImage}
                                            className={`relative cursor-pointer aspect-square w-full overflow-hidden rounded-[10px] border transition-all duration-150 ${
                                                item &&
                                                selectedMediaIds.includes(
                                                    item.id
                                                )
                                                    ? 'border-black  dark:border-sky-blue-2 ring-2  ring-black dark:ring-sky-blue-2 scale-95'
                                                    : 'border-black/5 dark:border-white/10'
                                            } ${
                                                !hasImage
                                                    ? 'cursor-default'
                                                    : 'hover:border-black dark:hover:border-sky-blue-2'
                                            } ${libraryLoading ? 'animate-pulse' : ''}`}
                                        >
                                            {hasImage ? (
                                                <img
                                                    src={item.url}
                                                    alt={
                                                        item.name ||
                                                        t(
                                                            'media.miniToolBoard.mediaAlt'
                                                        )
                                                    }
                                                    className="h-full w-full object-cover"
                                                />
                                            ) : (
                                                <div className="absolute inset-0 bg-gradient-to-br from-[var(--color-grey-7)] via-white to-[var(--color-grey-7)] dark:from-[#2a3234] dark:via-[#1a2124] dark:to-[#0f171a]" />
                                            )}
                                        </button>
                                    )
                                }
                            )}
                        </div>

                        <button
                            type="button"
                            onClick={handleToggleBrowseMore}
                            className="mt-4 flex w-full underline cursor-pointer items-center justify-center rounded-[12px] px-3 py-3 text-xs font-semibold transition"
                        >
                            {myLibraryOpen
                                ? t('media.miniToolBoard.closeLibrary')
                                : t('media.miniToolBoard.browseMore')}
                        </button>
                    </div>
                    <div className="border-t border-black/10 dark:border-white/10">
                        {(() => {
                            const { minImages, maxImages } = getImageLimits()
                            const selectedCount = selectedMediaIds.length
                            const selectionCountLabel =
                                selectedCount === 1
                                    ? t(
                                          'media.miniToolBoard.selectionCountSingle',
                                          {
                                              count: selectedCount,
                                              max: maxImages
                                          }
                                      )
                                    : t(
                                          'media.miniToolBoard.selectionCountPlural',
                                          {
                                              count: selectedCount,
                                              max: maxImages
                                          }
                                      )

                            const getSelectedUrl = (mediaId: string) => {
                                return (
                                    libraryItems.find((m) => m.id === mediaId)
                                        ?.url ||
                                    userMediaItems.find((m) => m.id === mediaId)
                                        ?.url
                                )
                            }

                            const handleRemoveSelected = (mediaId: string) => {
                                setSelectedMediaIds((prev) =>
                                    prev.filter((id) => id !== mediaId)
                                )
                            }

                            return (
                                <>
                                    <div className="mt-3 flex items-center justify-between">
                                        <span className="text-xs font-semibold text-black dark:text-white/80">
                                            {t(
                                                'media.miniToolBoard.selectedLabel'
                                            )}
                                        </span>
                                        <span className="text-[11px] text-black dark:text-grey-1">
                                            {selectedCount > 0
                                                ? selectionCountLabel
                                                : minImages > 1
                                                  ? t(
                                                        'media.miniToolBoard.selectRange',
                                                        {
                                                            min: minImages,
                                                            max: maxImages
                                                        }
                                                    )
                                                  : t(
                                                        'media.miniToolBoard.noItems'
                                                    )}
                                        </span>
                                    </div>
                                    <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                                        {selectedMediaIds.map((mediaId) => {
                                            const url = getSelectedUrl(mediaId)
                                            return (
                                                <div
                                                    key={mediaId}
                                                    className="relative h-[56px] w-[56px] overflow-hidden shrink-0 rounded-[10px] bg-white dark:bg-[#0f1316] transition-all duration-150 group"
                                                >
                                                    {url ? (
                                                        <img
                                                            src={url}
                                                            alt={t(
                                                                'media.miniToolBoard.selectedAlt'
                                                            )}
                                                            className="h-full w-full object-cover"
                                                        />
                                                    ) : (
                                                        <div className="h-full w-full bg-grey-7" />
                                                    )}
                                                    <button
                                                        type="button"
                                                        onClick={() =>
                                                            handleRemoveSelected(
                                                                mediaId
                                                            )
                                                        }
                                                        className="z-100 absolute top-1 right-1 h-3 w-3 rounded-full bg-white text-xs flex items-center justify-center"
                                                    >
                                                        <Icon
                                                            name="close-circle"
                                                            className="fill-red-2"
                                                        />
                                                    </button>
                                                </div>
                                            )
                                        })}
                                        {selectedMediaIds.length === 0 && (
                                            <div className="h-[56px] w-[56px] shrink-0 overflow-hidden rounded-[10px] border border-black/10 dark:border-white/10 bg-white dark:bg-[#0f1316]">
                                                <div className="h-full w-full bg-grey-7" />
                                            </div>
                                        )}
                                    </div>
                                </>
                            )
                        })()}

                        <div className="mt-4 flex justify-center">
                            <Button
                                size="sm"
                                variant="secondary"
                                className="rounded-lg h-[42px] bg-firefly dark:bg-sky-blue-2 px-6 py-3 text-sm font-semibold text-sky-blue-2 dark:text-black disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-sky-blue-2"
                                onClick={handleConfirmSelection}
                                disabled={
                                    selectedMediaIds.length <
                                    getImageLimits().minImages
                                }
                            >
                                {t('media.miniToolBoard.confirm')}
                            </Button>
                        </div>
                    </div>
                </div>

                <div
                    ref={myLibraryRef}
                    className={`max-h-[85vh] rounded-xl bg-white text-[#0b1419]  dark:border-white/10 dark:bg-[#181E1C] dark:text-white flex flex-col transition-all duration-200 ${
                        myLibraryOpen
                            ? 'w-full md:max-w-[90vw] sm:w-[420px] sm:max-w-[420px] p-4 opacity-100 sm:h-[85vh] sm:max-h-[85vh] overflow-hidden rounded-l-none'
                            : 'w-0 sm:w-0 p-0 opacity-0 pointer-events-none overflow-hidden'
                    }`}
                >
                    {myLibraryOpen && (
                        <>
                            <div className="relative mb-4 flex items-center shrink-0">
                                <Button
                                    size="icon"
                                    variant="ghost"
                                    className="size-6"
                                    onClick={() => setMyLibraryOpen(false)}
                                    title={t('common.goBack')}
                                >
                                    <Icon
                                        name="sidebar-close"
                                        className="size-6"
                                    />
                                </Button>
                                <span className="ml-3 text-sm font-semibold">
                                    {t('media.miniToolBoard.myLibraryTitle')}
                                </span>
                                <Button
                                    size="icon"
                                    variant="ghost"
                                    className="absolute right-0 h-8 w-8 rounded-full    "
                                    onClick={onClear}
                                    title={t('common.close')}
                                >
                                    <Icon name="close-2" className="size-6" />
                                </Button>
                            </div>

                            {userMediaLoading && (
                                <p className="text-center text-[11px] text-[#6b7280] dark:text-grey-1 shrink-0">
                                    {t(
                                        'media.miniToolBoard.loadingYourLibrary'
                                    )}
                                </p>
                            )}

                            <div className="flex-1 overflow-y-auto min-h-0">
                                <div className="grid grid-cols-4 gap-2">
                                    {Array.from({
                                        length: Math.max(
                                            userMediaItems.length,
                                            32
                                        )
                                    }).map((_, index) => {
                                        const item = userMediaItems[index]
                                        if (item) {
                                            return (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() =>
                                                        handleSelectFromMyLibrary(
                                                            item
                                                        )
                                                    }
                                                    className={`relative cursor-pointer aspect-square w-full overflow-hidden rounded-[10px] border transition-all duration-150 ${
                                                        selectedMediaIds.includes(
                                                            item.id
                                                        )
                                                            ? 'border-black  dark:border-sky-blue-2 ring-2  ring-black dark:ring-sky-blue-2'
                                                            : 'border-black/10 hover:border-black dark:border-white/10'
                                                    }`}
                                                >
                                                    <img
                                                        src={item.url}
                                                        alt={
                                                            item.name ||
                                                            t(
                                                                'media.miniToolBoard.mediaAlt'
                                                            )
                                                        }
                                                        className="h-full w-full object-cover"
                                                    />
                                                </button>
                                            )
                                        }

                                        return (
                                            <div
                                                key={`empty-${index}`}
                                                className={`aspect-square w-full rounded-[10px] bg-grey-7 ${
                                                    userMediaLoading
                                                        ? 'animate-pulse'
                                                        : ''
                                                }`}
                                            />
                                        )
                                    })}
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    )
}

export default MiniToolBoardOverlay
