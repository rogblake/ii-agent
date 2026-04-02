import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, ReactElement } from 'react'

import { AnimatePresence, motion } from 'framer-motion'
import type { TFunction } from 'i18next'
import JSZip from 'jszip'
import { jsPDF } from 'jspdf'
import HTMLFlipBook from 'react-pageflip'
import { Trans, useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle
} from '@/components/ui/dialog'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Loader2, TriangleAlert } from 'lucide-react'
import {
    Popover,
    PopoverAnchor,
    PopoverContent,
    PopoverTrigger
} from '@/components/ui/popover'
import {
    StorybookPageRenderer,
    StorybookPageThumbnail,
    triggerPageMathRender
} from '@/components/ui/storybook-page-renderer'
import {
    useStorybook,
    type StorybookImage,
    type StorybookPageData
} from '@/contexts/storybook-context'
import {
    StorybookEditProvider,
    useStorybookEdit
} from '@/contexts/storybook-edit-context'
import { cn } from '@/lib/utils'
import { fileService } from '@/services/file.service'
import { chatService } from '@/services/chat.service'
import {
    storybookService,
    type DesignChange,
    type Storybook,
    type VersionInfo
} from '@/services/storybook.service'
import ShareConversation from '@/components/agent/share-conversation'
import { StorybookEditWrapper } from '@/components/storybook/storybook-edit-wrapper'
import { StorybookInspectorPanel } from '@/components/storybook/storybook-inspector-panel'
import type { ElementInfo } from '@/components/design-mode/types'
import { Logo } from '@/components/logo'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { useIsMobile } from '@/hooks/use-mobile'
import { getStorybookLanguageFromLocale } from '@/utils/storybook-language'
import { useAppDispatch, userApi } from '@/state'

const BOOK_SCALE = 0.92
const AUTO_PLAY_DELAY_MS = 10000
const MAX_AUDIO_WAIT_MS = 180000

const getInitialViewportHeight = (): number => {
    return typeof window === 'undefined' ? 0 : window.innerHeight
}

const calculateBookDimensions = (
    containerWidth: number,
    containerHeight: number,
    pageAspectRatio = 1,
    isDouble = true
): { pageWidth: number; pageHeight: number } => {
    if (!containerWidth || !containerHeight) {
        return { pageWidth: 0, pageHeight: 0 }
    }

    const availableWidth = containerWidth * BOOK_SCALE
    const availableHeight = containerHeight * BOOK_SCALE
    const ratio = pageAspectRatio > 0 ? pageAspectRatio : 1

    const maxPageWidthFromWidth = isDouble ? availableWidth / 2 : availableWidth
    const maxPageWidthFromHeight = availableHeight * ratio
    const pageWidth = Math.min(maxPageWidthFromWidth, maxPageWidthFromHeight)
    const pageHeight = pageWidth / ratio

    return { pageWidth, pageHeight }
}

type DownloadedPage = {
    blob: Blob
    pageNumber: number
}

type SaveResult = {
    storybook: Storybook | null
    voiceSuccess: boolean
}

const extractStoragePathFromUrl = (url: string): string | null => {
    try {
        const parsed = new URL(url)
        const parts = parsed.pathname.replace(/^\/+/, '').split('/')
        const sessionsIndex = parts.indexOf('sessions')
        const relevant = sessionsIndex >= 0 ? parts.slice(sessionsIndex) : parts
        if (!relevant.length) return null
        return decodeURIComponent(relevant.join('/'))
    } catch {
        return null
    }
}

const blobToDataUrl = (blob: Blob): Promise<string> =>
    new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onloadend = () => resolve(reader.result as string)
        reader.onerror = reject
        reader.readAsDataURL(blob)
    })

const IMAGE_EXTENSION_REGEX = /\.(png|jpe?g|gif|webp|bmp|svg|tiff?|avif)$/i

const preloadImage = (url: string): Promise<void> =>
    new Promise((resolve) => {
        if (typeof Image === 'undefined') {
            resolve()
            return
        }
        const img = new Image()
        img.onload = () => resolve()
        img.onerror = () => resolve()
        img.src = url
    })

/**
 * Convert CSS property name (kebab-case) to computedStyles key (camelCase)
 * e.g., "text-align" -> "textAlign", "font-weight" -> "fontWeight"
 */
const cssPropertyToComputedStyleKey = (
    property: string
): keyof ElementInfo['computedStyles'] | null => {
    const map: Record<string, keyof ElementInfo['computedStyles']> = {
        'font-family': 'fontFamily',
        'font-size': 'fontSize',
        'font-weight': 'fontWeight',
        'font-style': 'fontStyle',
        color: 'color',
        'background-color': 'backgroundColor',
        'background-image': 'backgroundImage',
        'background-clip': 'backgroundClip',
        '-webkit-background-clip': 'webkitBackgroundClip',
        '-webkit-text-fill-color': 'webkitTextFillColor',
        'border-radius': 'borderRadius',
        'border-image': 'borderImageSource',
        'border-image-source': 'borderImageSource',
        'border-color': 'borderColor',
        'border-style': 'borderStyle',
        'border-width': 'borderWidth',
        padding: 'padding',
        margin: 'margin',
        'line-height': 'lineHeight',
        'letter-spacing': 'letterSpacing',
        'text-align': 'textAlign',
        'text-decoration-line': 'textDecorationLine',
        'text-transform': 'textTransform',
        opacity: 'opacity',
        width: 'width',
        height: 'height',
        'box-shadow': 'boxShadow'
    }
    return map[property] ?? null
}

/**
 * Update selectedElement's computedStyles and textContent with the given changes
 */
const updateSelectedElementWithChanges = (
    selectedElement: ElementInfo | null,
    changes: DesignChange[],
    useFromValue: boolean
): ElementInfo | null => {
    if (!selectedElement) return null

    // Check if any change affects the selected element
    const relevantChanges = changes.filter(
        (change) => change.designId === selectedElement.designId
    )

    if (relevantChanges.length === 0) return null

    // Create updated element
    let updatedElement = { ...selectedElement }
    const updatedStyles = { ...selectedElement.computedStyles }
    const updatedAttributes = { ...(selectedElement.attributes ?? {}) }
    let hasUpdates = false

    for (const change of relevantChanges) {
        if (change.type === 'style') {
            const styleKey = cssPropertyToComputedStyleKey(change.property)
            if (styleKey) {
                const newValue = useFromValue
                    ? change.value.from
                    : change.value.to
                ;(updatedStyles as Record<string, string | undefined>)[
                    styleKey
                ] = newValue ?? undefined
                hasUpdates = true
            }
        } else if (change.type === 'text') {
            const newValue = useFromValue ? change.value.from : change.value.to
            updatedElement = {
                ...updatedElement,
                textContent: newValue ?? ''
            }
            hasUpdates = true
        } else if (change.type === 'attribute') {
            const newValue = useFromValue ? change.value.from : change.value.to
            if (newValue == null) {
                delete updatedAttributes[change.property]
            } else {
                updatedAttributes[change.property] = newValue
            }
            hasUpdates = true
        }
    }

    if (!hasUpdates) return null

    // Return updated element with updated styles
    return {
        ...updatedElement,
        computedStyles: updatedStyles,
        attributes: updatedAttributes
    }
}

const getImageDimensions = (
    dataUrl: string
): Promise<{ width: number; height: number }> =>
    new Promise((resolve, reject) => {
        const img = new Image()
        img.onload = () =>
            resolve({
                width: img.naturalWidth || img.width,
                height: img.naturalHeight || img.height
            })
        img.onerror = () => reject(new Error('Failed to load image'))
        img.src = dataUrl
    })

const PDF_MAX_IMAGE_DIMENSION = 1920
const PDF_JPEG_QUALITY = 0.75

const convertAndResizeImageForPdf = (
    dataUrl: string,
    quality: number = PDF_JPEG_QUALITY,
    maxDimension: number = PDF_MAX_IMAGE_DIMENSION
): Promise<string> =>
    new Promise((resolve, reject) => {
        const img = new Image()
        img.onload = () => {
            let targetWidth = img.naturalWidth || img.width
            let targetHeight = img.naturalHeight || img.height

            // Resize if larger than max dimension to reduce file size
            if (targetWidth > maxDimension || targetHeight > maxDimension) {
                const ratio = Math.min(
                    maxDimension / targetWidth,
                    maxDimension / targetHeight
                )
                targetWidth = Math.round(targetWidth * ratio)
                targetHeight = Math.round(targetHeight * ratio)
            }

            const canvas = document.createElement('canvas')
            canvas.width = targetWidth
            canvas.height = targetHeight
            const ctx = canvas.getContext('2d')
            if (!ctx) {
                reject(new Error('Failed to get canvas context'))
                return
            }
            // Fill with white background (JPEG doesn't support transparency)
            ctx.fillStyle = '#FFFFFF'
            ctx.fillRect(0, 0, canvas.width, canvas.height)
            // Use high-quality image scaling
            ctx.imageSmoothingEnabled = true
            ctx.imageSmoothingQuality = 'high'
            ctx.drawImage(img, 0, 0, targetWidth, targetHeight)
            resolve(canvas.toDataURL('image/jpeg', quality))
        }
        img.onerror = () =>
            reject(new Error('Failed to load image for conversion'))
        img.src = dataUrl
    })

const triggerBlobDownload = (blob: Blob, filename: string): void => {
    const downloadUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(downloadUrl)
}

const buildBaseFilename = (name: string, fallback: string): string => {
    const cleaned = name
        .trim()
        .replace(/\.[^/.]+$/, '')
        .replace(/[^a-zA-Z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
    return cleaned || fallback
}

const formatRelativeTime = (
    t: TFunction,
    dateString: string | null
): string => {
    if (!dateString) return ''

    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSeconds = Math.floor(diffMs / 1000)
    const diffMinutes = Math.floor(diffSeconds / 60)
    const diffHours = Math.floor(diffMinutes / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffSeconds < 60) {
        return t('storybook.modal.time.justNow')
    } else if (diffMinutes < 60) {
        return t('storybook.modal.time.minutesAgo', { count: diffMinutes })
    } else if (diffHours < 24) {
        return t('storybook.modal.time.hoursAgo', { count: diffHours })
    } else if (diffDays < 7) {
        return t('storybook.modal.time.daysAgo', { count: diffDays })
    } else {
        return date.toLocaleDateString()
    }
}

const createPdfFromPages = async (
    pages: DownloadedPage[],
    filename: string
): Promise<void> => {
    if (!pages.length) {
        throw new Error('No pages to include in PDF')
    }

    const preparedPages = await Promise.all(
        pages.map(async (page) => {
            const dataUrl = await blobToDataUrl(page.blob)
            // Convert and resize image to reduce PDF file size
            const jpegDataUrl = await convertAndResizeImageForPdf(dataUrl)
            // Get dimensions of the processed image
            const { width, height } = await getImageDimensions(jpegDataUrl)
            return { dataUrl: jpegDataUrl, width, height }
        })
    )

    const doc = new jsPDF({
        unit: 'px',
        format: [preparedPages[0].width, preparedPages[0].height],
        compress: true
    })

    preparedPages.forEach((page, idx) => {
        if (idx > 0) {
            doc.addPage([page.width, page.height])
        }
        // Use JPEG format with MEDIUM compression for better quality/size balance
        doc.addImage(
            page.dataUrl,
            'JPEG',
            0,
            0,
            page.width,
            page.height,
            undefined,
            'MEDIUM'
        )
    })

    doc.save(`${filename}.pdf`)
}

const createPngDownload = async (
    pages: DownloadedPage[],
    baseName: string,
    scope: 'current' | 'all'
): Promise<void> => {
    if (!pages.length) {
        throw new Error('No pages available for PNG download')
    }

    if (scope === 'current') {
        const page = pages[0]
        triggerBlobDownload(
            page.blob,
            `${baseName}-page-${page.pageNumber}.png`
        )
        return
    }

    const zip = new JSZip()
    pages.forEach((page) => {
        zip.file(`page-${page.pageNumber}.png`, page.blob)
    })
    const zipBlob = await zip.generateAsync({ type: 'blob' })
    triggerBlobDownload(zipBlob, `${baseName}-pages.zip`)
}

// Inner component that uses the edit context
function StorybookModalInner({
    isShareMode,
    publicView
}: {
    isShareMode: boolean
    publicView: boolean
}): ReactElement | null {
    const { t, i18n } = useTranslation()
    const navigate = useNavigate()
    const dispatch = useAppDispatch()
    const isSage = useIsSageTheme()
    const isMobile = useIsMobile()
    const {
        isModalOpen,
        images,
        closeModal,
        currentStorybook,
        switchToVersion,
        refreshAfterEdit
    } = useStorybook()
    const {
        isEditMode,
        editingStorybookId,
        currentEditPage,
        pageChanges,
        selectedElement,
        hasUnsavedChanges,
        isSaving,
        enterEditMode,
        exitEditMode,
        setCurrentEditPage,
        setSelectedElement,
        addChange,
        undoLastChange,
        getPageChanges,
        getPageHasChanges,
        getPagesWithChanges,
        setPageImageUrl,
        saveAllChanges,
        discardAllChanges,
        totalChangesCount
    } = useStorybookEdit()

    // Determine if we're using new storybook data or legacy images
    const useNewFormat = Boolean(
        currentStorybook && currentStorybook.pages.length > 0
    )
    const pages: StorybookPageData[] = useNewFormat
        ? currentStorybook!.pages
        : images.map((img, idx) => ({
              id: `legacy-${idx}`,
              pageNumber: idx + 1,
              displayPageNumber: idx + 1, // Legacy images are all image pages
              imageUrl: img.url,
              imagePrompt: null,
              textContent: null,
              textPosition: 'none' as const,
              textPercentage: 0,
              htmlContent: null,
              metadata: null
          }))

    const hasAudio = useMemo(
        () => pages.some((page) => Boolean(page.audioLink)),
        [pages]
    )

    // Check if storybook uses separate_page mode (has text-only pages)
    const hasSeparateTextPages = pages.some(
        (page) => page.metadata?.is_text_only_page === true
    )

    const isMangaMode =
        currentStorybook?.styleJson?.manga_layout === true

    const bookRef = useRef<any>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [currentPage, setCurrentPage] = useState(0)
    const currentPageRef = useRef(0)
    const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
    const [description, setDescription] = useState('')
    const [isRegeneratingImage, setIsRegeneratingImage] = useState(false)
    const [referenceImageUrl, setReferenceImageUrl] = useState<string | null>(
        null
    )
    const [referenceImageName, setReferenceImageName] = useState<string | null>(
        null
    )
    const [isUploadingReference, setIsUploadingReference] = useState(false)
    const [hostWidth, setHostWidth] = useState(0)
    const [modalLeft, setModalLeft] = useState(0)
    const [viewportHeight, setViewportHeight] = useState(
        getInitialViewportHeight
    )
    const [pageAspectRatio, setPageAspectRatio] = useState(1)
    const [viewMode, setViewMode] = useState<'single' | 'double'>('double')
    const [isAutoPlayEnabled, setIsAutoPlayEnabled] = useState(false)
    const [downloadFormat, setDownloadFormat] = useState<'pdf' | 'png'>('pdf')
    const [isDownloading, setIsDownloading] = useState(false)
    const [downloadScope, setDownloadScope] = useState<
        'current' | 'all' | null
    >(null)
    const [isShareOpen, setIsShareOpen] = useState(false)
    const [isVoiceEnabled, setIsVoiceEnabled] = useState(false)
    const [isVoicePromptOpen, setIsVoicePromptOpen] = useState(false)
    const [isGeneratingVoice, setIsGeneratingVoice] = useState(false)
    const [isSaveFinalizing, setIsSaveFinalizing] = useState(false)
    const [autoPlayRestartToken, setAutoPlayRestartToken] = useState(0)
    const audioRef = useRef<HTMLAudioElement | null>(null)
    // Track which page the selected element belongs to (for separate_page mode with multiple iframes)
    const [selectedElementPage, setSelectedElementPage] = useState<
        number | null
    >(null)
    const selectedElementBaseRef = useRef<ElementInfo | null>(null)
    const [isChangesOpen, setIsChangesOpen] = useState(false)
    const [isVersionsOpen, setIsVersionsOpen] = useState(false)
    const [isUnsavedChangesOpen, setIsUnsavedChangesOpen] = useState(false)
    const [pendingAction, setPendingAction] = useState<
        'exit-edit' | 'close-modal' | null
    >(null)
    const [versionHistory, setVersionHistory] = useState<VersionInfo[]>([])
    const [isLoadingVersions, setIsLoadingVersions] = useState(false)
    const [selectedChangeKeys, setSelectedChangeKeys] = useState<Set<string>>(
        () => new Set()
    )
    const [redoStack, setRedoStack] = useState<Map<number, DesignChange[][]>>(
        () => new Map()
    )
    const lastEditActionRef = useRef<'undo' | 'redo' | null>(null)
    const referenceFileInputRef = useRef<HTMLInputElement>(null)
    const resumePageRef = useRef<number | null>(null)
    const editThumbsRef = useRef<HTMLDivElement>(null)
    const viewerThumbsRef = useRef<HTMLDivElement>(null)
    const isSavingEdits = isSaving || isSaveFinalizing

    const stopAudio = useCallback(() => {
        if (!audioRef.current) return
        audioRef.current.pause()
        audioRef.current.currentTime = 0
        audioRef.current.src = ''
    }, [])

    useEffect(() => {
        currentPageRef.current = currentPage
    }, [currentPage])

    const getIframeTitle = useCallback(
        (page: number) => t('storybook.editWrapper.iframeTitle', { page }),
        [t]
    )

    const queueResumePageFromEdit = useCallback(() => {
        if (!currentEditPage || pages.length === 0) return
        const maxIndex = Math.max(pages.length - 1, 0)
        resumePageRef.current = Math.min(
            Math.max(currentEditPage - 1, 0),
            maxIndex
        )
    }, [currentEditPage, pages.length])

    useEffect(() => {
        if (isModalOpen) {
            setCurrentPage(0)
            // Reset book to first page when opening
            if (bookRef.current?.pageFlip()) {
                try {
                    bookRef.current.pageFlip().flip(0)
                } catch (e) {
                    // ignore
                }
            }
        }
    }, [isModalOpen, pages.length])

    useEffect(() => {
        if (hasSeparateTextPages && viewMode !== 'double') {
            setViewMode('double')
        }
    }, [hasSeparateTextPages, viewMode])

    useEffect(() => {
        if (!isModalOpen || isEditMode) return

        const resumeIndex = resumePageRef.current
        if (resumeIndex !== null) {
            const maxIndex = Math.max(pages.length - 1, 0)
            const targetIndex = Math.min(Math.max(resumeIndex, 0), maxIndex)
            setCurrentPage(targetIndex)
            if (bookRef.current?.pageFlip()) {
                try {
                    bookRef.current.pageFlip().flip(targetIndex)
                } catch (e) {
                    // ignore
                }
            }
            resumePageRef.current = null
            return
        }

        setCurrentPage(0)
        if (bookRef.current?.pageFlip()) {
            try {
                bookRef.current.pageFlip().flip(0)
            } catch (e) {
                // ignore
            }
        }
    }, [
        currentStorybook?.id,
        currentStorybook?.version,
        pages.length,
        isModalOpen,
        isEditMode
    ])

    // Exit edit mode when modal closes (discard unsaved changes)
    useEffect(() => {
        if (!isModalOpen && isEditMode) {
            exitEditMode()
        }
    }, [isModalOpen, isEditMode, exitEditMode])

    useEffect(() => {
        if (!isModalOpen) {
            setReferenceImageUrl(null)
            setReferenceImageName(null)
            resumePageRef.current = null
            setIsAutoPlayEnabled(false)
            setIsVoiceEnabled(false)
            setIsVoicePromptOpen(false)
            setIsGeneratingVoice(false)
            setIsSaveFinalizing(false)
        }
    }, [isModalOpen])

    useEffect(() => {
        if (!isModalOpen) return
        setIsVoiceEnabled(hasAudio)
    }, [isModalOpen, hasAudio])

    useEffect(() => {
        if (!isAutoPlayEnabled) {
            stopAudio()
        }
    }, [isAutoPlayEnabled, stopAudio])

    const isAtEnd = useCallback(() => {
        if (pages.length === 0) return true
        if (isMobile || viewMode === 'single') {
            return currentPage >= pages.length - 1
        }
        const leftIndex =
            currentPage === 0
                ? 0
                : currentPage % 2 === 1
                  ? currentPage
                  : currentPage - 1
        return leftIndex >= pages.length - 2 && leftIndex > 0
    }, [currentPage, pages.length, viewMode, isMobile])

    useEffect(() => {
        if (!isEditMode || !editThumbsRef.current) return
        const targetPage = currentEditPage || 1
        const target = editThumbsRef.current.querySelector(
            `[data-thumb-page="${targetPage}"]`
        )
        if (target && target instanceof HTMLElement) {
            target.scrollIntoView({
                behavior: 'smooth',
                inline: 'center',
                block: 'nearest'
            })
        }
    }, [isEditMode, currentEditPage])

    // Clear selected element when navigating between edit pages
    useEffect(() => {
        selectedElementBaseRef.current = null
        setSelectedElement(null)
        setSelectedElementPage(null)
    }, [currentEditPage, setSelectedElement])

    useEffect(() => {
        if (
            lastEditActionRef.current !== 'undo' &&
            lastEditActionRef.current !== 'redo'
        ) {
            setRedoStack(new Map())
        }
    }, [pageChanges])

    useEffect(() => {
        if (!selectedElement) {
            selectedElementBaseRef.current = null
        }
    }, [selectedElement])

    useEffect(() => {
        if (!isModalOpen) return

        const updateHostMetrics = () => {
            if (typeof window !== 'undefined') {
                setViewportHeight(window.innerHeight)
            }
            const homeContainer = document.getElementById('chat-wrapper')
            if (homeContainer) {
                setHostWidth(homeContainer.clientWidth)
                setModalLeft(homeContainer.offsetLeft)
            } else if (typeof window !== 'undefined') {
                setHostWidth(window.innerWidth)
                setModalLeft(0)
            }
        }

        updateHostMetrics()
        window.addEventListener('resize', updateHostMetrics)

        return () => {
            window.removeEventListener('resize', updateHostMetrics)
        }
    }, [isModalOpen])

    const modalWidth = hostWidth

    useEffect(() => {
        const updateSize = () => {
            if (containerRef.current) {
                const { clientWidth, clientHeight } = containerRef.current
                setContainerSize({ width: clientWidth, height: clientHeight })
            }
        }

        if (isModalOpen) {
            window.addEventListener('resize', updateSize)
            updateSize()
            // Multiple updates to ensure proper sizing after layout changes
            const timer1 = setTimeout(updateSize, 0)
            const timer2 = setTimeout(updateSize, 50)
            const timer3 = setTimeout(updateSize, 150)
            return () => {
                window.removeEventListener('resize', updateSize)
                clearTimeout(timer1)
                clearTimeout(timer2)
                clearTimeout(timer3)
            }
        }

        return () => {
            window.removeEventListener('resize', updateSize)
        }
    }, [isModalOpen, hostWidth, viewportHeight, viewMode, isMobile])

    // Force container size update when viewMode changes
    useEffect(() => {
        if (isModalOpen && containerRef.current) {
            const updateSize = () => {
                if (containerRef.current) {
                    const { clientWidth, clientHeight } = containerRef.current
                    setContainerSize({
                        width: clientWidth,
                        height: clientHeight
                    })
                }
            }

            // Immediate update
            updateSize()

            // Delayed updates to catch any layout shifts
            const timers = [
                setTimeout(updateSize, 0),
                setTimeout(updateSize, 50),
                setTimeout(updateSize, 100),
                setTimeout(updateSize, 200)
            ]

            return () => {
                timers.forEach((timer) => clearTimeout(timer))
            }
        }
    }, [viewMode, isModalOpen])

    useEffect(() => {
        if (!pages.length) return

        // For new format with HTML, use the aspect ratio from storybook metadata
        if (useNewFormat && currentStorybook?.aspectRatio) {
            const [w, h] = currentStorybook.aspectRatio.split(':').map(Number)
            if (w && h) {
                setPageAspectRatio(w / h)
                return
            }
        }

        // Fallback: calculate from first page image
        const firstImageUrl = pages[0]?.imageUrl
        if (!firstImageUrl) {
            setPageAspectRatio(16 / 9) // Default to 16:9
            return
        }

        let isMounted = true
        const img = new Image()

        img.onload = () => {
            if (!isMounted) return
            const ratio =
                img.naturalWidth && img.naturalHeight
                    ? img.naturalWidth / img.naturalHeight
                    : 1
            setPageAspectRatio(ratio > 0 ? ratio : 1)
        }

        img.onerror = () => {
            if (isMounted) setPageAspectRatio(16 / 9)
        }

        img.src = firstImageUrl

        return () => {
            isMounted = false
        }
    }, [pages, useNewFormat, currentStorybook?.aspectRatio])

    const handleFlip = useCallback(
        (e: any) => {
            setCurrentPage(e.data)

            // Trigger KaTeX rendering for the current and adjacent pages after flip animation
            setTimeout(() => {
                const currentPageIndex = e.data
                if (pages[currentPageIndex]) {
                    triggerPageMathRender(pages[currentPageIndex].id)
                }
                // Also render adjacent pages
                if (pages[currentPageIndex + 1]) {
                    triggerPageMathRender(pages[currentPageIndex + 1].id)
                }
                if (pages[currentPageIndex - 1]) {
                    triggerPageMathRender(pages[currentPageIndex - 1].id)
                }
            }, 200) // Wait for flip animation to complete
        },
        [pages]
    )

    // Handle book initialization
    const handleInit = useCallback(() => {
        // Render math for first few pages on init
        setTimeout(() => {
            for (let i = 0; i < Math.min(3, pages.length); i++) {
                if (pages[i]) {
                    triggerPageMathRender(pages[i].id)
                }
            }
        }, 300)
    }, [pages])

    const scrollToPageOnMobile = useCallback((pageIndex: number) => {
        if (!containerRef.current) return
        const pageElement = containerRef.current.querySelector(
            `[data-page-index="${pageIndex}"]`
        )
        if (pageElement) {
            pageElement.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
    }, [])

    const nextPage = useCallback(() => {
        if (isMobile) {
            const nextIndex = Math.min(currentPage + 1, pages.length - 1)
            setCurrentPage(nextIndex)
            scrollToPageOnMobile(nextIndex)
        } else if (viewMode === 'double' && bookRef.current?.pageFlip()) {
            bookRef.current.pageFlip().flipNext()
        } else if (viewMode === 'single') {
            setCurrentPage((prev) => Math.min(prev + 1, pages.length - 1))
        }
    }, [isMobile, viewMode, pages.length, currentPage, scrollToPageOnMobile])

    const prevPage = useCallback(() => {
        if (isMobile) {
            const prevIndex = Math.max(currentPage - 1, 0)
            setCurrentPage(prevIndex)
            scrollToPageOnMobile(prevIndex)
        } else if (viewMode === 'double' && bookRef.current?.pageFlip()) {
            bookRef.current.pageFlip().flipPrev()
        } else if (viewMode === 'single') {
            setCurrentPage((prev) => Math.max(prev - 1, 0))
        }
    }, [isMobile, viewMode, currentPage, scrollToPageOnMobile])

    const handleVoiceToggle = useCallback(() => {
        if (isGeneratingVoice) return

        if (hasAudio) {
            setIsVoiceEnabled((prev) => !prev)
            return
        }

        if (!useNewFormat || !currentStorybook?.id) {
            toast.error(t('storybook.voiceOver.toasts.unavailable'))
            return
        }

        setIsVoicePromptOpen((prev) => !prev)
    }, [
        isGeneratingVoice,
        hasAudio,
        useNewFormat,
        currentStorybook?.id,
        t,
        setIsVoiceEnabled,
        setIsVoicePromptOpen
    ])

    const handleGenerateVoiceOver = useCallback(
        async (
            storybookIdOverride?: string,
            options?: { force?: boolean; suppressToast?: boolean }
        ): Promise<boolean> => {
            if (isGeneratingVoice) return false
            if (!useNewFormat) return false
            const overrideId =
                typeof storybookIdOverride === 'string'
                    ? storybookIdOverride
                    : undefined
            const storybookId = overrideId ?? currentStorybook?.id
            if (!storybookId) return false
            const shouldShowToast = !options?.suppressToast

            setIsVoicePromptOpen(false)
            setIsGeneratingVoice(true)
            try {
                const storedLanguage =
                    currentStorybook?.styleJson?.language_code as
                        | string
                        | undefined
                const language =
                    storedLanguage ||
                    getStorybookLanguageFromLocale(i18n.language)
                const response =
                    await storybookService.generateStorybookVoiceOver(
                        storybookId,
                        language,
                        options
                    )
                const responsePages = response.storybook?.pages || []
                const hasAnyAudio = responsePages.some((page) =>
                    Boolean(page.audio_link)
                )
                const shouldTreatAsSuccess =
                    response.success ||
                    (options?.force && response.storybook && hasAnyAudio)
                if (shouldTreatAsSuccess && response.storybook) {
                    refreshAfterEdit(response.storybook)
                    if (hasAnyAudio) {
                        setIsVoiceEnabled(true)
                    }
                    if (isAutoPlayEnabled && hasAnyAudio) {
                        const separateTextPages = responsePages.some(
                            (page) => page.metadata?.is_text_only_page === true
                        )
                        const resolveLinks = (): string[] => {
                            if (responsePages.length === 0) return []
                            if (viewMode === 'single') {
                                const link =
                                    responsePages[currentPage]?.audio_link
                                return link ? [link] : []
                            }
                            if (!separateTextPages && currentPage === 0) {
                                const link = responsePages[0]?.audio_link
                                return link ? [link] : []
                            }
                            const leftIndex =
                                currentPage === 0
                                    ? 0
                                    : currentPage % 2 === 1
                                      ? currentPage
                                      : currentPage - 1
                            const rightIndex = leftIndex + 1
                            const indices: number[] = [leftIndex]
                            if (rightIndex < responsePages.length) {
                                indices.push(rightIndex)
                            }
                            const ordered =
                                separateTextPages &&
                                viewMode === 'double' &&
                                indices.length > 1
                                    ? [indices[1], indices[0]]
                                    : indices
                            return ordered
                                .map(
                                    (index) => responsePages[index]?.audio_link
                                )
                                .filter((link): link is string => Boolean(link))
                        }
                        if (resolveLinks().length === 0 && !isAtEnd()) {
                            setTimeout(() => {
                                nextPage()
                            }, 0)
                        }
                        setAutoPlayRestartToken((prev) => prev + 1)
                    }
                    if (response.success && shouldShowToast) {
                        toast.success(t('storybook.voiceOver.toasts.generated'))
                    }
                    return true
                } else {
                    if (shouldShowToast) {
                        toast.error(
                            response.error ||
                                t('storybook.voiceOver.toasts.failed')
                        )
                    }
                    return false
                }
            } catch (error) {
                console.error(
                    '[Storybook] Voice over generation failed:',
                    error
                )
                if (shouldShowToast) {
                    toast.error(t('storybook.voiceOver.toasts.failed'))
                }
                return false
            } finally {
                setIsGeneratingVoice(false)
            }
        },
        [
            currentStorybook?.id,
            i18n.language,
            isGeneratingVoice,
            isAutoPlayEnabled,
            currentPage,
            refreshAfterEdit,
            viewMode,
            nextPage,
            isAtEnd,
            t,
            useNewFormat,
            setIsGeneratingVoice,
            setIsVoicePromptOpen,
            setIsVoiceEnabled
        ]
    )

    const handleVoicePromptOpenChange = useCallback(
        (open: boolean) => {
            if (isGeneratingVoice) return
            setIsVoicePromptOpen(open)
        },
        [isGeneratingVoice, setIsVoicePromptOpen]
    )

    const renderVoiceOverPrompt = () => (
        <PopoverContent
            align="end"
            sideOffset={10}
            className="w-[360px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-black/5 bg-white p-0 text-black shadow-2xl dark:bg-white dark:text-black"
        >
            <div className="px-6 pt-6 text-left">
                <div className="flex items-center gap-2 text-base font-semibold text-black">
                    <Icon name="voice" className="size-5" />
                    {t('storybook.voiceOver.title')}
                </div>
            </div>
            <div className="px-6 text-black">
                <div className="mt-4 flex justify-center">
                    <div className="relative flex h-44 w-44 items-center justify-center rounded-full bg-[#f5efe3]">
                        <Icon name="voice-over" className="w-36 h-auto" />
                    </div>
                </div>
                <p className="mt-4 text-sm text-gray-600">
                    {t('storybook.voiceOver.description')}
                </p>
            </div>
            <div className="mt-4 grid w-full grid-cols-2 gap-3 px-6 pb-6">
                <Button
                    onClick={() => {
                        void handleGenerateVoiceOver()
                    }}
                    disabled={isGeneratingVoice}
                    className="h-10 w-full gap-2 rounded-xl bg-[#cfe9f4] text-black hover:bg-[#b8e0f0]"
                >
                    {isGeneratingVoice && (
                        <Loader2 className="size-4 animate-spin" />
                    )}
                    {t('storybook.voiceOver.generate')}
                </Button>
                <Button
                    variant="ghost"
                    onClick={() => setIsVoicePromptOpen(false)}
                    disabled={isGeneratingVoice}
                    className="h-10 w-full text-red-500 hover:bg-red-50 hover:text-red-600"
                >
                    {t('common.cancel')}
                </Button>
            </div>
        </PopoverContent>
    )

    const getCurrentAudioLinks = useCallback(() => {
        if (!useNewFormat || pages.length === 0) return null

        // On mobile, treat like single page mode
        if (isMobile || viewMode === 'single') {
            const link = pages[currentPage]?.audioLink
            return link ? [link] : []
        }

        if (!hasSeparateTextPages && currentPage === 0) {
            const coverLink = pages[0]?.audioLink
            return coverLink ? [coverLink] : []
        }

        const leftIndex =
            currentPage === 0
                ? 0
                : currentPage % 2 === 1
                  ? currentPage
                  : currentPage - 1
        const rightIndex = leftIndex + 1
        const indices: number[] = [leftIndex]
        if (rightIndex < pages.length) {
            indices.push(rightIndex)
        }

        // In separate_page mode, narration usually lives on the right (text) page.
        const orderedIndices =
            hasSeparateTextPages && viewMode === 'double' && indices.length > 1
                ? [indices[1], indices[0]]
                : indices

        return orderedIndices
            .map((idx) => pages[idx]?.audioLink)
            .filter((link): link is string => Boolean(link))
    }, [
        currentPage,
        hasSeparateTextPages,
        isMobile,
        pages,
        useNewFormat,
        viewMode
    ])

    const currentAudioLinks = useMemo(
        () => getCurrentAudioLinks() ?? [],
        [getCurrentAudioLinks]
    )

    useEffect(() => {
        if (
            !isModalOpen ||
            isEditMode ||
            !isAutoPlayEnabled ||
            pages.length <= 1
        ) {
            return
        }

        let timeoutId: number | null = null
        let isCancelled = false

        const scheduleNextPage = (delayMs: number) => {
            timeoutId = window.setTimeout(() => {
                if (isCancelled) return
                if (isAtEnd()) {
                    stopAudio()
                    setIsAutoPlayEnabled(false)
                    return
                }
                nextPage()
            }, delayMs)
        }

        const playSingleAudio = (link: string): Promise<boolean> =>
            new Promise((resolve) => {
                const audio = audioRef.current ?? new Audio()
                audioRef.current = audio
                let fallbackId: number | null = null
                let lastProgressTime = 0
                let lastProgressAt = Date.now()
                const clearFallback = () => {
                    if (fallbackId) {
                        window.clearTimeout(fallbackId)
                        fallbackId = null
                    }
                }
                const finish = (played: boolean) => {
                    clearFallback()
                    audio.onended = null
                    audio.onerror = null
                    audio.onloadedmetadata = null
                    audio.onplaying = null
                    audio.ontimeupdate = null
                    resolve(played)
                }
                const scheduleFallback = (ms: number) => {
                    clearFallback()
                    fallbackId = window.setTimeout(() => {
                        if (audio.ended) {
                            finish(true)
                            return
                        }
                        if (
                            audio.currentTime > 0 &&
                            Date.now() - lastProgressAt < 2000
                        ) {
                            scheduleFallback(1000)
                            return
                        }
                        finish(false)
                    }, ms)
                }

                audio.onended = () => finish(true)
                audio.onerror = () => finish(false)
                audio.onplaying = () => {
                    scheduleFallback(1000)
                }
                audio.ontimeupdate = () => {
                    if (audio.currentTime > lastProgressTime + 0.05) {
                        lastProgressTime = audio.currentTime
                        lastProgressAt = Date.now()
                    }
                }
                audio.onloadedmetadata = () => {
                    const durationMs = Number.isFinite(audio.duration)
                        ? audio.duration * 1000 + 500
                        : AUTO_PLAY_DELAY_MS
                    if (audio.paused) {
                        scheduleFallback(
                            Math.min(durationMs, MAX_AUDIO_WAIT_MS)
                        )
                    }
                }

                scheduleFallback(AUTO_PLAY_DELAY_MS)
                if (audio.src !== link) {
                    audio.src = link
                } else {
                    audio.currentTime = 0
                }
                const playPromise = audio.play()
                if (playPromise?.catch) {
                    playPromise.catch(() => finish(false))
                }
            })

        const playAudioSequence = async (links: string[]) => {
            if (!links.length) return false
            let played = false
            for (const link of links) {
                if (isCancelled) return false
                const ok = await playSingleAudio(link)
                if (ok) {
                    played = true
                }
            }
            return played
        }

        if (isAutoPlayEnabled && isVoiceEnabled && currentAudioLinks.length) {
            void playAudioSequence(currentAudioLinks).then((played) => {
                if (isCancelled) return
                scheduleNextPage(played ? 0 : AUTO_PLAY_DELAY_MS)
            })
        } else {
            stopAudio()
            scheduleNextPage(AUTO_PLAY_DELAY_MS)
        }

        return () => {
            isCancelled = true
            if (timeoutId) {
                window.clearTimeout(timeoutId)
            }
            if (audioRef.current) {
                audioRef.current.onended = null
                audioRef.current.onerror = null
            }
        }
    }, [
        isModalOpen,
        isEditMode,
        isAutoPlayEnabled,
        isVoiceEnabled,
        currentAudioLinks,
        pages.length,
        nextPage,
        stopAudio,
        isAtEnd,
        autoPlayRestartToken
    ])

    useEffect(() => {
        if (isEditMode || !viewerThumbsRef.current) return
        const activeIndex =
            viewMode === 'single'
                ? currentPage
                : currentPage === 0
                  ? 0
                  : currentPage % 2 === 1
                    ? currentPage
                    : currentPage - 1
        const target = viewerThumbsRef.current.querySelector(
            `[data-thumb-index="${activeIndex}"]`
        )
        if (target && target instanceof HTMLElement) {
            target.scrollIntoView({
                behavior: 'smooth',
                inline: 'center',
                block: 'nearest'
            })
        }
    }, [isEditMode, currentPage, viewMode])

    const markEditAction = useCallback((action: 'undo' | 'redo') => {
        lastEditActionRef.current = action
        setTimeout(() => {
            if (lastEditActionRef.current === action) {
                lastEditActionRef.current = null
            }
        }, 0)
    }, [])

    const buildSelectedElementFromChanges = useCallback(
        (changes: DesignChange[]) => {
            const baseElement =
                selectedElementBaseRef.current || selectedElement
            if (!baseElement) return null
            const updated = updateSelectedElementWithChanges(
                baseElement,
                changes,
                false
            )
            return updated ?? baseElement
        },
        [selectedElement]
    )

    const handleUndo = useCallback(() => {
        if (!currentEditPage) return

        // In separate_page mode, check both pages and find the one with most recent change
        const pagesToCheck = [currentEditPage]
        if (hasSeparateTextPages && currentEditPage >= 2) {
            pagesToCheck.push(currentEditPage + 1)
        }

        let targetPage = currentEditPage
        let latestTimestamp = 0
        for (const page of pagesToCheck) {
            const pageChanges = getPageChanges(page)
            if (pageChanges.length > 0) {
                const maxTimestamp = Math.max(
                    ...pageChanges.map((c) => c.timestamp)
                )
                if (maxTimestamp > latestTimestamp) {
                    latestTimestamp = maxTimestamp
                    targetPage = page
                }
            }
        }

        const changes = getPageChanges(targetPage)
        if (changes.length === 0) return

        const latest = changes.reduce((acc, change) =>
            change.timestamp > acc.timestamp ? change : acc
        )
        const batch = latest.groupId
            ? changes.filter((change) => change.groupId === latest.groupId)
            : [latest]
        const batchSet = new Set(batch)
        const remainingChanges = changes.filter(
            (change) => !batchSet.has(change)
        )

        setRedoStack((prev) => {
            const next = new Map(prev)
            const existing = next.get(targetPage) ?? []
            next.set(targetPage, [batch, ...existing])
            return next
        })

        // Send revert messages to iframe to sync visual state
        const iframe = document.querySelector(
            `iframe[title="${getIframeTitle(targetPage)}"]`
        ) as HTMLIFrameElement

        if (iframe?.contentWindow) {
            batch.forEach((change) => {
                if (change.type === 'style') {
                    iframe.contentWindow!.postMessage(
                        {
                            type: 'DESIGN_MODE_SET_STYLE',
                            payload: {
                                designId: change.designId,
                                property: change.property,
                                value: change.value.from,
                                skipTracking: true
                            }
                        },
                        '*'
                    )
                } else if (change.type === 'text') {
                    iframe.contentWindow!.postMessage(
                        {
                            type: 'DESIGN_MODE_SET_TEXT',
                            payload: {
                                designId: change.designId,
                                text: change.value.from,
                                skipTracking: true
                            }
                        },
                        '*'
                    )
                } else if (change.type === 'attribute') {
                    if (change.property === 'icon') {
                        const raw = change.value.from ?? ''
                        let iconName = ''
                        let svgInner = ''
                        try {
                            const parsed = JSON.parse(raw) as
                                | { name?: unknown; svg?: unknown }
                                | undefined
                            iconName =
                                parsed && typeof parsed.name === 'string'
                                    ? parsed.name
                                    : ''
                            svgInner =
                                parsed && typeof parsed.svg === 'string'
                                    ? parsed.svg
                                    : ''
                        } catch {
                            svgInner = raw
                        }

                        if (svgInner) {
                            iframe.contentWindow!.postMessage(
                                {
                                    type: 'DESIGN_MODE_SET_ICON',
                                    payload: {
                                        designId: change.designId,
                                        iconName,
                                        svgInner,
                                        xpath: change.elementContext?.xpath,
                                        skipTracking: true
                                    }
                                },
                                '*'
                            )
                        }
                    } else {
                        iframe.contentWindow!.postMessage(
                            {
                                type: 'DESIGN_MODE_SET_ATTRIBUTE',
                                payload: {
                                    designId: change.designId,
                                    attribute: change.property,
                                    value: change.value.from,
                                    xpath: change.elementContext?.xpath,
                                    skipTracking: true
                                }
                            },
                            '*'
                        )
                    }
                }
            })
        }

        // Update selectedElement's computedStyles to reflect reverted values
        // This ensures the inspector panel syncs its local state
        const selectedPage = selectedElementPage || currentEditPage
        const selectedPageChanges =
            selectedPage === targetPage
                ? remainingChanges
                : selectedPage
                  ? getPageChanges(selectedPage)
                  : []
        const updatedElement =
            selectedPageChanges.length > 0
                ? buildSelectedElementFromChanges(selectedPageChanges)
                : selectedElementBaseRef.current || selectedElement
        if (updatedElement) {
            setSelectedElement(updatedElement)
        }

        markEditAction('undo')
        undoLastChange(targetPage)
    }, [
        currentEditPage,
        getPageChanges,
        markEditAction,
        undoLastChange,
        hasSeparateTextPages,
        selectedElement,
        setSelectedElement,
        selectedElementPage,
        buildSelectedElementFromChanges,
        getIframeTitle
    ])

    const handleRedo = useCallback(() => {
        if (!currentEditPage) return

        // In separate_page mode, check both pages and find the one with redo items
        const pagesToCheck = [currentEditPage]
        if (hasSeparateTextPages && currentEditPage >= 2) {
            pagesToCheck.push(currentEditPage + 1)
        }

        let targetPage = currentEditPage
        let foundRedo = false
        for (const page of pagesToCheck) {
            const pageBatches = redoStack.get(page)
            if (pageBatches && pageBatches.length > 0) {
                targetPage = page
                foundRedo = true
                break
            }
        }

        if (!foundRedo) return

        const batches = redoStack.get(targetPage)
        if (!batches || batches.length === 0) return

        const [batch, ...rest] = batches
        const changes = getPageChanges(targetPage)
        setRedoStack((prev) => {
            const next = new Map(prev)
            if (rest.length === 0) {
                next.delete(targetPage)
            } else {
                next.set(targetPage, rest)
            }
            return next
        })

        // Send re-apply messages to iframe to sync visual state
        const iframe = document.querySelector(
            `iframe[title="${getIframeTitle(targetPage)}"]`
        ) as HTMLIFrameElement

        if (iframe?.contentWindow) {
            batch.forEach((change) => {
                if (change.type === 'style') {
                    iframe.contentWindow!.postMessage(
                        {
                            type: 'DESIGN_MODE_SET_STYLE',
                            payload: {
                                designId: change.designId,
                                property: change.property,
                                value: change.value.to,
                                skipTracking: true
                            }
                        },
                        '*'
                    )
                } else if (change.type === 'text') {
                    iframe.contentWindow!.postMessage(
                        {
                            type: 'DESIGN_MODE_SET_TEXT',
                            payload: {
                                designId: change.designId,
                                text: change.value.to,
                                skipTracking: true
                            }
                        },
                        '*'
                    )
                } else if (change.type === 'attribute') {
                    if (change.property === 'icon') {
                        const raw = change.value.to ?? ''
                        let iconName = ''
                        let svgInner = ''
                        try {
                            const parsed = JSON.parse(raw) as
                                | { name?: unknown; svg?: unknown }
                                | undefined
                            iconName =
                                parsed && typeof parsed.name === 'string'
                                    ? parsed.name
                                    : ''
                            svgInner =
                                parsed && typeof parsed.svg === 'string'
                                    ? parsed.svg
                                    : ''
                        } catch {
                            svgInner = raw
                        }

                        if (svgInner) {
                            iframe.contentWindow!.postMessage(
                                {
                                    type: 'DESIGN_MODE_SET_ICON',
                                    payload: {
                                        designId: change.designId,
                                        iconName,
                                        svgInner,
                                        xpath: change.elementContext?.xpath,
                                        skipTracking: true
                                    }
                                },
                                '*'
                            )
                        }
                    } else {
                        iframe.contentWindow!.postMessage(
                            {
                                type: 'DESIGN_MODE_SET_ATTRIBUTE',
                                payload: {
                                    designId: change.designId,
                                    attribute: change.property,
                                    value: change.value.to,
                                    xpath: change.elementContext?.xpath,
                                    skipTracking: true
                                }
                            },
                            '*'
                        )
                    }
                }
            })
        }

        // Update selectedElement's computedStyles to reflect re-applied values
        // This ensures the inspector panel syncs its local state
        const selectedPage = selectedElementPage || currentEditPage
        const nextTargetChanges = [...changes, ...batch]
        const selectedPageChanges =
            selectedPage === targetPage
                ? nextTargetChanges
                : selectedPage
                  ? getPageChanges(selectedPage)
                  : []
        const updatedElement =
            selectedPageChanges.length > 0
                ? buildSelectedElementFromChanges(selectedPageChanges)
                : selectedElementBaseRef.current || selectedElement
        if (updatedElement) {
            setSelectedElement(updatedElement)
        }

        markEditAction('redo')
        batch.forEach((change, index) => {
            addChange(targetPage, {
                ...change,
                timestamp: Date.now() + index
            })
        })
    }, [
        addChange,
        currentEditPage,
        markEditAction,
        redoStack,
        hasSeparateTextPages,
        selectedElement,
        setSelectedElement,
        getPageChanges,
        selectedElementPage,
        buildSelectedElementFromChanges,
        getIframeTitle
    ])

    const handleClearAll = useCallback(() => {
        // Get all pages with changes
        const pagesWithChanges = getPagesWithChanges()

        // Revert all changes in each iframe
        pagesWithChanges.forEach((pageNumber) => {
            const changes = getPageChanges(pageNumber)
            const iframe = document.querySelector(
                `iframe[title="${getIframeTitle(pageNumber)}"]`
            ) as HTMLIFrameElement

            if (iframe?.contentWindow) {
                changes.forEach((change) => {
                    if (change.type === 'style') {
                        iframe.contentWindow!.postMessage(
                            {
                                type: 'DESIGN_MODE_SET_STYLE',
                                payload: {
                                    designId: change.designId,
                                    property: change.property,
                                    value: change.value.from,
                                    skipTracking: true
                                }
                            },
                            '*'
                        )
                    } else if (change.type === 'text') {
                        iframe.contentWindow!.postMessage(
                            {
                                type: 'DESIGN_MODE_SET_TEXT',
                                payload: {
                                    designId: change.designId,
                                    text: change.value.from,
                                    skipTracking: true
                                }
                            },
                            '*'
                        )
                    } else if (change.type === 'attribute') {
                        if (change.property === 'icon') {
                            const raw = change.value.from ?? ''
                            let iconName = ''
                            let svgInner = ''
                            try {
                                const parsed = JSON.parse(raw) as
                                    | { name?: unknown; svg?: unknown }
                                    | undefined
                                iconName =
                                    parsed && typeof parsed.name === 'string'
                                        ? parsed.name
                                        : ''
                                svgInner =
                                    parsed && typeof parsed.svg === 'string'
                                        ? parsed.svg
                                        : ''
                            } catch {
                                svgInner = raw
                            }

                            if (svgInner) {
                                iframe.contentWindow!.postMessage(
                                    {
                                        type: 'DESIGN_MODE_SET_ICON',
                                        payload: {
                                            designId: change.designId,
                                            iconName,
                                            svgInner,
                                            xpath: change.elementContext?.xpath,
                                            skipTracking: true
                                        }
                                    },
                                    '*'
                                )
                            }
                        } else {
                            iframe.contentWindow!.postMessage(
                                {
                                    type: 'DESIGN_MODE_SET_ATTRIBUTE',
                                    payload: {
                                        designId: change.designId,
                                        attribute: change.property,
                                        value: change.value.from,
                                        xpath: change.elementContext?.xpath,
                                        skipTracking: true
                                    }
                                },
                                '*'
                            )
                        }
                    }
                })
            }
        })

        // Reset selected element to base state to sync inspector panel
        // This ensures the inspector panel shows original values
        const baseElement = selectedElementBaseRef.current
        if (baseElement) {
            setSelectedElement({ ...baseElement })
        } else if (selectedElement) {
            // If no base ref, deselect to force re-selection with fresh state
            setSelectedElement(null)
        }

        // Clear redo stack
        setRedoStack(new Map())

        // Clear all tracked changes
        discardAllChanges()
    }, [
        getPagesWithChanges,
        getPageChanges,
        getIframeTitle,
        setSelectedElement,
        discardAllChanges,
        selectedElement
    ])

    const handleChangesOpenChange = useCallback(
        (open: boolean) => {
            setIsChangesOpen(open)
            if (open) {
                setIsVersionsOpen(false)
                // Select all changes by default when opening
                const allKeys = getPagesWithChanges().flatMap((pageNumber) => {
                    const groupKeys = new Set<string>()
                    return getPageChanges(pageNumber).reduce<string[]>(
                        (keys, change) => {
                            if (change.groupId) {
                                const key = `${pageNumber}-${change.groupId}`
                                if (!groupKeys.has(key)) {
                                    groupKeys.add(key)
                                    keys.push(key)
                                }
                                return keys
                            }
                            keys.push(
                                `${pageNumber}-${change.designId}-${change.property}-${change.timestamp}`
                            )
                            return keys
                        },
                        []
                    )
                })
                setSelectedChangeKeys(new Set(allKeys))
            }
        },
        [getPagesWithChanges, getPageChanges]
    )

    const toggleChangeSelection = useCallback((key: string) => {
        setSelectedChangeKeys((prev) => {
            const next = new Set(prev)
            if (next.has(key)) {
                next.delete(key)
            } else {
                next.add(key)
            }
            return next
        })
    }, [])

    const handleVersionsOpenChange = useCallback(
        async (open: boolean) => {
            setIsVersionsOpen(open)
            if (open) {
                setIsChangesOpen(false)
                // Fetch version history when opening
                if (currentStorybook?.id) {
                    setIsLoadingVersions(true)
                    try {
                        const response =
                            await storybookService.getVersionHistory(
                                currentStorybook.id
                            )
                        setVersionHistory(response.versions)
                    } catch (error) {
                        console.error('Failed to fetch version history:', error)
                        setVersionHistory([])
                    } finally {
                        setIsLoadingVersions(false)
                    }
                }
            }
        },
        [currentStorybook?.id]
    )

    const toggleChangesOpen = useCallback(() => {
        setIsChangesOpen((prev) => {
            const next = !prev
            if (next) {
                setIsVersionsOpen(false)
            }
            return next
        })
    }, [])

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (!isModalOpen) return

            const target = e.target as HTMLElement | null
            const isTypingField =
                target instanceof HTMLInputElement ||
                target instanceof HTMLTextAreaElement ||
                target?.isContentEditable
            const isShortcut = e.metaKey || e.ctrlKey

            if (isEditMode && isShortcut) {
                const key = e.key.toLowerCase()
                if (key === 's') {
                    e.preventDefault()
                    toggleChangesOpen()
                    return
                }
                if (key === 'z') {
                    if (isTypingField) return
                    e.preventDefault()
                    if (e.shiftKey) {
                        handleRedo()
                    } else {
                        handleUndo()
                    }
                    return
                }
                if (key === 'y') {
                    if (isTypingField) return
                    e.preventDefault()
                    handleRedo()
                    return
                }
            }

            if (isTypingField) return

            if (e.key === 'ArrowLeft') {
                e.preventDefault()
                if (isEditMode) {
                    const current = currentEditPage || 1
                    if (hasSeparateTextPages) {
                        // Page 1 is cover, pairs start from 2-3, 4-5, etc.
                        if (current === 2) {
                            setCurrentEditPage(1)
                        } else if (current > 2) {
                            setCurrentEditPage(current - 2)
                        }
                    } else {
                        setCurrentEditPage(Math.max(current - 1, 1))
                    }
                } else {
                    prevPage()
                }
            } else if (e.key === 'ArrowRight') {
                e.preventDefault()
                if (isEditMode) {
                    const current = currentEditPage || 1
                    if (hasSeparateTextPages) {
                        // Page 1 is cover, pairs start from 2-3, 4-5, etc.
                        if (current === 1) {
                            setCurrentEditPage(2)
                        } else if (current + 2 <= pages.length) {
                            setCurrentEditPage(current + 2)
                        }
                    } else {
                        setCurrentEditPage(Math.min(current + 1, pages.length))
                    }
                } else {
                    nextPage()
                }
            }
        }

        if (isModalOpen) {
            window.addEventListener('keydown', handleKeyDown)
        }

        return () => {
            window.removeEventListener('keydown', handleKeyDown)
        }
    }, [
        isModalOpen,
        nextPage,
        prevPage,
        isEditMode,
        currentEditPage,
        setCurrentEditPage,
        pages.length,
        hasSeparateTextPages,
        handleRedo,
        handleUndo,
        toggleChangesOpen
    ])

    const jumpToPage = (pageIndex: number) => {
        if (isMobile) {
            setCurrentPage(pageIndex)
            scrollToPageOnMobile(pageIndex)
        } else if (viewMode === 'double' && bookRef.current?.pageFlip()) {
            try {
                bookRef.current.pageFlip().flip(pageIndex)
            } catch (e) {
                // ignore
            }
        } else {
            setCurrentPage(pageIndex)
        }
    }

    // Get the current edit page's image URL for AI rewrite context
    const currentEditPageImageUrl = useMemo(() => {
        if (!currentEditPage || !pages.length) return null
        // Find the page that matches currentEditPage
        const page = pages.find((p) => p.pageNumber === currentEditPage)
        if (page?.imageUrl) return page.imageUrl
        // If current page is a text page (in separate_page mode), try to get the previous image page
        if (hasSeparateTextPages && currentEditPage > 1) {
            const prevPage = pages.find(
                (p) => p.pageNumber === currentEditPage - 1
            )
            if (prevPage?.imageUrl) return prevPage.imageUrl
        }
        return null
    }, [currentEditPage, pages, hasSeparateTextPages])

    const isImageSelected = selectedElement?.tagName?.toLowerCase() === 'img'
    const selectedImageSrc = isImageSelected
        ? selectedElement?.attributes?.src
        : null
    const canRegenerateImage = Boolean(isImageSelected && selectedImageSrc)
    const isDescribeDisabled = !canRegenerateImage || isRegeneratingImage
    const isRegenerateSubmitDisabled =
        isDescribeDisabled || !description.trim() || isUploadingReference
    const isAttachDisabled = isDescribeDisabled || isUploadingReference

    const getImageOverrideForPage = useCallback(
        (pageNumber: number): string | null => {
            const changes = getPageChanges(pageNumber)
            if (!changes.length) return null

            const srcChanges = changes.filter(
                (change) =>
                    change.type === 'attribute' && change.property === 'src'
            )
            if (!srcChanges.length) return null

            const latest = srcChanges.reduce((acc, change) =>
                change.timestamp > acc.timestamp ? change : acc
            )
            return latest.value.to ?? null
        },
        [getPageChanges]
    )

    const handleReferenceUploadClick = useCallback(() => {
        referenceFileInputRef.current?.click()
    }, [])

    const handleReferenceUploadChange = useCallback(
        async (event: ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.[0]
            if (!file) return
            event.target.value = ''

            const hasImageType = file.type.startsWith('image/')
            const hasImageExt = IMAGE_EXTENSION_REGEX.test(file.name || '')
            if (!hasImageType && !hasImageExt) {
                toast.error(t('storybook.modal.toasts.invalidImageFile'))
                return
            }

            const storybookId = editingStorybookId || currentStorybook?.id
            if (!storybookId) {
                toast.error(t('storybook.modal.toasts.referenceAttachFailed'))
                return
            }

            setIsUploadingReference(true)
            try {
                const result = await storybookService.uploadBackgroundImage(
                    storybookId,
                    file
                )
                setReferenceImageUrl(result.url)
                setReferenceImageName(
                    file.name || t('storybook.modal.reference.defaultName')
                )
            } catch (error) {
                console.error(
                    '[StorybookEdit] Failed to upload reference image:',
                    error
                )
                toast.error(t('storybook.modal.toasts.referenceUploadFailed'))
            } finally {
                setIsUploadingReference(false)
            }
        },
        [editingStorybookId, currentStorybook?.id, t]
    )

    const clearReferenceImage = useCallback(() => {
        setReferenceImageUrl(null)
        setReferenceImageName(null)
    }, [])

    const extractSceneTextFromIframe = useCallback(
        (pageNumber: number | null) => {
            if (!pageNumber) return ''
            const iframe = document.querySelector(
                `iframe[title="${getIframeTitle(pageNumber)}"]`
            ) as HTMLIFrameElement | null
            const doc = iframe?.contentDocument
            if (!doc) return ''
            const nodes = Array.from(
                doc.querySelectorAll('[data-editable="text"]')
            )
            const text = nodes
                .map((node) => node.textContent?.trim())
                .filter((value): value is string => Boolean(value))
                .join(' ')
            return text
        },
        [getIframeTitle]
    )

    const getSceneText = useCallback(() => {
        const imagePage = selectedElementPage || currentEditPage
        if (!imagePage) return ''

        if (hasSeparateTextPages && imagePage >= 2) {
            const textPage = imagePage + 1
            if (textPage <= pages.length) {
                const text = extractSceneTextFromIframe(textPage)
                if (text) return text
            }
        }

        return extractSceneTextFromIframe(imagePage)
    }, [
        currentEditPage,
        selectedElementPage,
        hasSeparateTextPages,
        pages.length,
        extractSceneTextFromIframe
    ])

    const performSave = useCallback(
        async (
            selectedKeys?: Set<string>,
            options?: { exitAfterSave?: boolean }
        ): Promise<SaveResult> => {
            if (isSaving || isSaveFinalizing) {
                return { storybook: null, voiceSuccess: false }
            }
            const newStorybook = await saveAllChanges(selectedKeys)
            if (!newStorybook) {
                return { storybook: null, voiceSuccess: false }
            }

            refreshAfterEdit(newStorybook)
            setSelectedChangeKeys(new Set())
            setVersionHistory([])

            // Invalidate credit cache to refresh balance after save (voice regeneration may have deducted credits)
            dispatch(
                userApi.util.invalidateTags(['CreditBalance', 'CreditUsage'])
            )

            // Voice regeneration is now handled by the backend during save
            // Only pages with text changes will have their voice regenerated
            toast.success(t('storybook.modal.toasts.changesSaved'))
            if (options?.exitAfterSave) {
                queueResumePageFromEdit()
                exitEditMode()
            }
            return { storybook: newStorybook, voiceSuccess: true }
        },
        [
            isSaving,
            isSaveFinalizing,
            saveAllChanges,
            refreshAfterEdit,
            dispatch,
            queueResumePageFromEdit,
            exitEditMode,
            t
        ]
    )

    // Handle save edits - saves all changes (used by main save button)
    const handleSaveEdits = useCallback(async () => {
        await performSave(undefined, { exitAfterSave: true })
    }, [performSave])

    // Handle save selected changes only (used by changes panel)
    const handleSaveSelectedChanges = useCallback(async () => {
        await performSave(selectedChangeKeys)
    }, [performSave, selectedChangeKeys])

    // Handle cancel edit mode
    const handleCancelEdit = useCallback(() => {
        if (isSavingEdits) return
        if (hasUnsavedChanges) {
            setPendingAction('exit-edit')
            setIsUnsavedChangesOpen(true)
        } else {
            queueResumePageFromEdit()
            exitEditMode()
        }
    }, [
        hasUnsavedChanges,
        exitEditMode,
        queueResumePageFromEdit,
        isSavingEdits
    ])

    const setSelectedElementWithBase = useCallback(
        (element: ElementInfo | null) => {
            selectedElementBaseRef.current = element
            setSelectedElement(element)
        },
        [setSelectedElement]
    )

    const handleEditModeVersionSelect = useCallback(
        (storybookId: string) => {
            if (hasUnsavedChanges) {
                const shouldDiscard = window.confirm(
                    t('storybook.modal.confirm.discardChanges')
                )
                if (!shouldDiscard) return
            }

            setIsVersionsOpen(false)
            setIsChangesOpen(false)
            setSelectedElementWithBase(null)
            setSelectedElementPage(null)

            setTimeout(() => {
                switchToVersion(storybookId)
                enterEditMode(storybookId, 1)
            }, 100)
        },
        [
            enterEditMode,
            hasUnsavedChanges,
            setIsChangesOpen,
            setIsVersionsOpen,
            setSelectedElementPage,
            setSelectedElementWithBase,
            switchToVersion,
            t
        ]
    )

    // Handle element selection with page tracking (for separate_page mode)
    const handleElementSelect = useCallback(
        (pageNumber: number) => (element: ElementInfo | null) => {
            setSelectedElementWithBase(element)
            setSelectedElementPage(element ? pageNumber : null)

            if (!hasSeparateTextPages || !currentEditPage) return
            if (currentEditPage < 2) return

            const otherPage =
                pageNumber === currentEditPage
                    ? currentEditPage + 1
                    : currentEditPage

            if (otherPage === pageNumber || otherPage > pages.length) return

            const otherIframe = document.querySelector(
                `iframe[title="${getIframeTitle(otherPage)}"]`
            ) as HTMLIFrameElement | null

            if (otherIframe?.contentWindow) {
                otherIframe.contentWindow.postMessage(
                    { type: 'DESIGN_MODE_CLEAR_SELECTION' },
                    '*'
                )
            }
        },
        [
            setSelectedElementWithBase,
            setSelectedElementPage,
            hasSeparateTextPages,
            currentEditPage,
            pages.length,
            getIframeTitle
        ]
    )

    // Handle style changes from inspector
    const handleStyleChange = useCallback(
        (
            property: string,
            value: string,
            options?: { groupId?: string; groupLabel?: string }
        ) => {
            if (!selectedElement || !currentEditPage) return

            // Use selectedElementPage to target the correct iframe (important for separate_page mode)
            const targetPage = selectedElementPage || currentEditPage
            const iframe = document.querySelector(
                `iframe[title="${getIframeTitle(targetPage)}"]`
            ) as HTMLIFrameElement
            if (iframe?.contentWindow) {
                iframe.contentWindow.postMessage(
                    {
                        type: 'DESIGN_MODE_SET_STYLE',
                        payload: {
                            designId: selectedElement.designId,
                            property,
                            value,
                            groupId: options?.groupId,
                            groupLabel: options?.groupLabel
                        }
                    },
                    '*'
                )
            }
        },
        [selectedElement, currentEditPage, selectedElementPage, getIframeTitle]
    )

    // Handle text changes from inspector
    const handleTextChange = useCallback(
        (text: string) => {
            if (!selectedElement || !currentEditPage) return

            // Use selectedElementPage to target the correct iframe (important for separate_page mode)
            const targetPage = selectedElementPage || currentEditPage
            const iframe = document.querySelector(
                `iframe[title="${getIframeTitle(targetPage)}"]`
            ) as HTMLIFrameElement
            if (iframe?.contentWindow) {
                iframe.contentWindow.postMessage(
                    {
                        type: 'DESIGN_MODE_SET_TEXT',
                        payload: {
                            designId: selectedElement.designId,
                            text
                        }
                    },
                    '*'
                )
            }
        },
        [selectedElement, currentEditPage, selectedElementPage, getIframeTitle]
    )

    const handleRegenerateImage = useCallback(async () => {
        if (!canRegenerateImage || !selectedElement) return
        if (isRegeneratingImage) return

        const prompt = description.trim()
        if (!prompt) return

        const storybookId = editingStorybookId || currentStorybook?.id
        if (!storybookId) return

        const targetPage = selectedElementPage || currentEditPage
        if (!targetPage) return

        setIsRegeneratingImage(true)
        try {
            const sceneText = getSceneText()
            const textPosition =
                hasSeparateTextPages && targetPage >= 2
                    ? 'separate_page'
                    : undefined

            const response = await storybookService.aiRegenerateImage(
                storybookId,
                targetPage,
                prompt,
                referenceImageUrl || undefined,
                sceneText || undefined,
                textPosition
            )

            if (response.success && response.image_url) {
                const imageUrl = response.image_url
                const preload = preloadImage(imageUrl)
                const iframe = document.querySelector(
                    `iframe[title="${getIframeTitle(targetPage)}"]`
                ) as HTMLIFrameElement | null
                if (iframe?.contentWindow) {
                    const groupId = `regenerate-image-${Date.now()}`
                    iframe.contentWindow.postMessage(
                        {
                            type: 'DESIGN_MODE_SET_ATTRIBUTE',
                            payload: {
                                designId: selectedElement.designId,
                                attribute: 'src',
                                value: imageUrl,
                                xpath: selectedElement.xpath,
                                groupId,
                                groupLabel: t(
                                    'storybook.modal.changeGroups.regenerateImage'
                                )
                            }
                        },
                        '*'
                    )
                }
                await preload
                // Track the regenerated image URL for saving
                setPageImageUrl(targetPage, imageUrl)
                // Invalidate credit cache to refresh balance after image regeneration
                dispatch(
                    userApi.util.invalidateTags(['CreditBalance', 'CreditUsage'])
                )
                toast.success(t('storybook.modal.toasts.imageRegenerated'))
                setDescription('')
                setReferenceImageUrl(null)
                setReferenceImageName(null)
            } else {
                toast.error(
                    response.error ||
                        t('storybook.modal.toasts.imageRegenerateFailed')
                )
            }
        } catch (error) {
            console.error('[StorybookEdit] Regenerate image failed:', error)
            toast.error(t('storybook.modal.toasts.imageRegenerateFailed'))
        } finally {
            setIsRegeneratingImage(false)
        }
    }, [
        canRegenerateImage,
        selectedElement,
        isRegeneratingImage,
        description,
        editingStorybookId,
        currentStorybook?.id,
        selectedElementPage,
        currentEditPage,
        getSceneText,
        hasSeparateTextPages,
        referenceImageUrl,
        setPageImageUrl,
        dispatch,
        t,
        getIframeTitle
    ])

    if (!isModalOpen || pages.length === 0) return null

    const title = (() => {
        if (useNewFormat && currentStorybook?.name) {
            return currentStorybook.name
        }
        if (!pages[0]?.imageUrl) return t('storybook.viewer.title')
        const filename =
            pages[0].imageUrl.split('/').pop()?.split('?')[0] ||
            t('storybook.viewer.defaultTitle')
        return decodeURIComponent(filename)
    })()

    const versionLabel =
        useNewFormat && currentStorybook?.version
            ? t('storybook.versionSelector.versionLabel', {
                  version: currentStorybook.version
              })
            : null
    const showPublicHeader = publicView && !isEditMode

    const { pageWidth, pageHeight } = calculateBookDimensions(
        containerSize.width,
        containerSize.height,
        pageAspectRatio,
        viewMode === 'double'
    )
    const bookWidth =
        viewMode === 'double'
            ? Math.floor(pageWidth * 2)
            : Math.floor(pageWidth)
    const bookHeight = Math.floor(pageHeight)

    const editPageLabel = hasSeparateTextPages
        ? (currentEditPage || 1) === 1
            ? t('storybook.modal.editPage.cover', {
                  current: 1,
                  total: pages.length
              })
            : t('storybook.modal.editPage.range', {
                  start: currentEditPage || 1,
                  end: (currentEditPage || 1) + 1,
                  total: pages.length
              })
        : t('storybook.modal.editPage.single', {
              current: currentEditPage || 1,
              total: pages.length
          })

    const currentEditPageNumber = currentEditPage || 1
    const formatChangeLabel = (change: DesignChange) => {
        if (change.groupLabel && change.groupLabel.trim()) {
            return change.groupLabel.trim()
        }
        const propertyLabel = change.property
            ? change.property.replace(/[-_]+/g, ' ')
            : t('storybook.modal.changes.labels.change')
        switch (change.type) {
            case 'text':
                return t('storybook.modal.changes.labels.editText')
            case 'move':
                return t('storybook.modal.changes.labels.moveElement')
            case 'attribute':
                return t('storybook.modal.changes.labels.updateProperty', {
                    property: propertyLabel
                })
            case 'style':
            default:
                return t('storybook.modal.changes.labels.styleProperty', {
                    property: propertyLabel
                })
        }
    }
    const changeItems = getPagesWithChanges()
        .flatMap((pageNumber) => {
            const grouped = new Map<
                string,
                {
                    key: string
                    pageNumber: number
                    label: string
                    timestamp: number
                }
            >()
            const changes = getPageChanges(pageNumber)
            for (const change of changes) {
                if (change.groupId) {
                    const key = `${pageNumber}-${change.groupId}`
                    const existing = grouped.get(key)
                    const label =
                        change.groupLabel?.trim() ||
                        existing?.label ||
                        formatChangeLabel(change)
                    const timestamp = Math.max(
                        existing?.timestamp ?? 0,
                        change.timestamp
                    )
                    grouped.set(key, {
                        key,
                        pageNumber,
                        label,
                        timestamp
                    })
                } else {
                    const key = `${pageNumber}-${change.designId}-${change.property}-${change.timestamp}`
                    grouped.set(key, {
                        key,
                        pageNumber,
                        label: formatChangeLabel(change),
                        timestamp: change.timestamp
                    })
                }
            }
            return Array.from(grouped.values())
        })
        .sort((a, b) => b.timestamp - a.timestamp)
    // In separate_page mode, check both the image page and text page for changes
    const canUndo =
        Boolean(currentEditPage) &&
        (getPageHasChanges(currentEditPageNumber) ||
            (hasSeparateTextPages &&
                currentEditPageNumber >= 2 &&
                getPageHasChanges(currentEditPageNumber + 1)))
    const canRedo =
        Boolean(currentEditPage) &&
        ((redoStack.get(currentEditPageNumber)?.length ?? 0) > 0 ||
            (hasSeparateTextPages &&
                currentEditPageNumber >= 2 &&
                (redoStack.get(currentEditPageNumber + 1)?.length ?? 0) > 0))
    const versionEntries =
        versionHistory.length > 0
            ? versionHistory
            : currentStorybook
              ? [
                    {
                        id: currentStorybook.id,
                        version: currentStorybook.version,
                        created_at: null as string | null,
                        is_current: true
                    }
                ]
              : []

    const handleDownload = async (scope: 'current' | 'all') => {
        if (isDownloading) return

        setDownloadScope(scope)
        setIsDownloading(true)

        // Re-trigger KaTeX rendering immediately after state change
        // to ensure math stays visible during download
        setTimeout(() => {
            if (pages[currentPage]) {
                triggerPageMathRender(pages[currentPage].id)
            }
            if (pages[currentPage + 1]) {
                triggerPageMathRender(pages[currentPage + 1].id)
            }
            if (pages[currentPage - 1]) {
                triggerPageMathRender(pages[currentPage - 1].id)
            }
        }, 50)

        try {
            // For new format with HTML content, use server-side generation
            if (useNewFormat && currentStorybook) {
                const baseName = buildBaseFilename(
                    title,
                    t('storybook.viewer.defaultTitle')
                )
                const pageNumber = currentPage + 1

                if (downloadFormat === 'pdf') {
                    if (scope === 'current') {
                        // Download single page as PDF
                        const pdfBlob =
                            await storybookService.downloadStorybookPagePdf(
                                currentStorybook.id,
                                pageNumber
                            )
                        triggerBlobDownload(
                            pdfBlob,
                            `${baseName}-page-${pageNumber}.pdf`
                        )
                        toast.success(t('storybook.viewer.download.success'))
                        return
                    } else {
                        // Download all pages as PDF with progress
                        const progressGenerator =
                            await storybookService.downloadStorybookWithProgress(
                                currentStorybook.id
                            )

                        for await (const progress of progressGenerator) {
                            if (progress.type === 'error') {
                                throw new Error(
                                    progress.message || 'Download failed'
                                )
                            }
                            if (
                                progress.type === 'complete' &&
                                progress.pdf_base64 &&
                                progress.filename
                            ) {
                                storybookService.downloadPDFFile(
                                    progress.pdf_base64,
                                    progress.filename
                                )
                                toast.success(
                                    t('storybook.viewer.download.success')
                                )
                                return
                            }
                        }
                        return
                    }
                } else {
                    // Server-side PNG generation
                    if (scope === 'current') {
                        // Download single page as PNG
                        const pngBlob =
                            await storybookService.downloadStorybookPagePng(
                                currentStorybook.id,
                                pageNumber
                            )
                        triggerBlobDownload(
                            pngBlob,
                            `${baseName}-page-${pageNumber}.png`
                        )
                        toast.success(t('storybook.viewer.download.success'))
                        return
                    } else {
                        // Download all pages as ZIP (non-streaming for reliability)
                        const zipBlob =
                            await storybookService.downloadStorybookPngZip(
                                currentStorybook.id
                            )
                        triggerBlobDownload(zipBlob, `${baseName}-pages.zip`)
                        toast.success(t('storybook.viewer.download.success'))
                        return
                    }
                }
            }

            // Legacy download logic for storybooks with image URLs
            const targetPages = (
                scope === 'current' ? [pages[currentPage]] : pages
            )
                .filter((p) => p.imageUrl)
                .map((page, index) => ({
                    imageUrl: page.imageUrl!,
                    pageNumber:
                        scope === 'current' ? currentPage + 1 : index + 1
                }))

            if (targetPages.length === 0) {
                toast.error(t('storybook.viewer.download.noPages'))
                return
            }

            const storagePaths = targetPages.map(({ imageUrl }) =>
                extractStoragePathFromUrl(imageUrl)
            )

            if (storagePaths.some((path) => !path)) {
                toast.error(t('storybook.viewer.download.unableToPrepare'))
                return
            }

            const response = await fileService.generateDownloadUrls(
                storagePaths as string[]
            )
            const signedUrls = response?.signed_urls || []
            const fileIds = response?.file_ids || []

            const hasDownloadSources =
                (signedUrls.length === targetPages.length &&
                    signedUrls.some((url) => Boolean(url))) ||
                (fileIds.length === targetPages.length &&
                    fileIds.some((id) => Boolean(id)))

            if (!hasDownloadSources) {
                throw new Error(t('storybook.viewer.download.missingSources'))
            }

            const pageBlobs = await Promise.all(
                targetPages.map(async (_page, index) => {
                    // Prefer downloading through backend by file_id to avoid bucket CORS
                    const fileId = fileIds[index]
                    if (fileId) {
                        const blob = await chatService.getFileContent({
                            fileId
                        })
                        return {
                            blob,
                            pageNumber: targetPages[index].pageNumber
                        }
                    }

                    const signedUrl = signedUrls[index]
                    if (!signedUrl) {
                        throw new Error(
                            t('storybook.viewer.download.missingSourcePage', {
                                page: targetPages[index].pageNumber
                            })
                        )
                    }

                    const res = await fetch(signedUrl as string)
                    if (!res.ok) {
                        throw new Error(
                            t('storybook.viewer.download.failedFetchPage', {
                                page: targetPages[index].pageNumber
                            })
                        )
                    }
                    const blob = await res.blob()
                    return {
                        blob,
                        pageNumber: targetPages[index].pageNumber
                    }
                })
            )

            const baseName = buildBaseFilename(
                title,
                t('storybook.viewer.defaultTitle')
            )

            if (downloadFormat === 'pdf') {
                const suffix =
                    scope === 'current'
                        ? `page-${targetPages[0].pageNumber}`
                        : 'all-pages'
                await createPdfFromPages(pageBlobs, `${baseName}-${suffix}`)
            } else {
                await createPngDownload(pageBlobs, baseName, scope)
            }
        } catch (error) {
            console.error(error)
            toast.error(t('storybook.viewer.download.failed'))
        } finally {
            setIsDownloading(false)
            setDownloadScope(null)

            // Re-trigger KaTeX rendering after download state changes
            // because React re-renders may have created new DOM elements
            // but the KaTeX cache still marks pages as "rendered"
            setTimeout(() => {
                if (pages[currentPage]) {
                    triggerPageMathRender(pages[currentPage].id)
                }
                // Also render adjacent pages
                if (pages[currentPage + 1]) {
                    triggerPageMathRender(pages[currentPage + 1].id)
                }
                if (pages[currentPage - 1]) {
                    triggerPageMathRender(pages[currentPage - 1].id)
                }
            }, 100)
        }
    }

    const isCurrentDownloading = isDownloading && downloadScope === 'current'
    const isAllDownloading = isDownloading && downloadScope === 'all'

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="fixed inset-0 z-50 flex items-center"
                onClick={
                    publicView
                        ? undefined
                        : () => {
                              if (isSavingEdits) return
                              closeModal()
                          }
                }
            >
                <div className="pointer-events-none flex w-full">
                    <div
                        className="pointer-events-auto relative h-[calc(100vh)]"
                        style={{
                            width: `${modalWidth}px`,
                            marginLeft: `${modalLeft}px`
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div
                            className={cn(
                                'relative flex w-full flex-col overflow-hidden rounded-2xl bg-white text-black dark:bg-[#181e1c] dark:text-white h-full',
                                showPublicHeader ? 'pt-0' : 'pt-5'
                            )}
                        >
                            {isEditMode && (
                                <div className="pointer-events-none absolute inset-y-0 right-[28rem] z-40 hidden w-px bg-black/10 md:block dark:bg-white/10" />
                            )}
                            {/* Header */}
                            {isEditMode && currentStorybook ? (
                                <div className="grid md:grid-cols-[minmax(0,1fr)_28rem]">
                                    <div className="flex flex-col w-full">
                                        <div className="relative z-30 grid h-12 grid-cols-[1fr_auto_1fr] items-center">
                                            <div className="flex items-center gap-3 ml-4">
                                                <Button
                                                    size="icon"
                                                    onClick={() => {
                                                        if (isSavingEdits)
                                                            return
                                                        if (hasUnsavedChanges) {
                                                            setPendingAction(
                                                                'close-modal'
                                                            )
                                                            setIsUnsavedChangesOpen(
                                                                true
                                                            )
                                                        } else {
                                                            closeModal()
                                                        }
                                                    }}
                                                    disabled={isSavingEdits}
                                                    className="h-10 w-10"
                                                >
                                                    <Icon
                                                        name="close-2"
                                                        className="size-5 fill-black/70 dark:fill-white/80"
                                                    />
                                                </Button>
                                            </div>

                                            <div className="flex min-w-0 items-center justify-center gap-2 px-2 sm:px-4">
                                                <Icon
                                                    name="image-2"
                                                    className="size-4 flex-shrink-0 fill-black/50 dark:fill-white/50"
                                                />
                                                <span className="max-w-[200px] truncate text-sm font-medium sm:max-w-md">
                                                    {title}
                                                </span>
                                                {versionLabel && (
                                                    <Popover
                                                        open={isVersionsOpen}
                                                        onOpenChange={
                                                            handleVersionsOpenChange
                                                        }
                                                    >
                                                        <PopoverTrigger asChild>
                                                            <Button
                                                                size="sm"
                                                                className="h-6 px-2 rounded-full text-xs whitespace-nowrap border border-sky-blue/40 bg-sky-blue/30 text-firefly hover:bg-sky-blue/40 dark:border-transparent dark:bg-[#bee6f0]/20 dark:text-[#bee6f0] dark:hover:bg-[#bee6f0]/30"
                                                            >
                                                                {versionLabel}
                                                            </Button>
                                                        </PopoverTrigger>
                                                        <PopoverContent
                                                            align="center"
                                                            className="w-72 rounded-xl border border-gray-200 bg-white dark:bg-white p-0 shadow-xl overflow-hidden text-black dark:text-black"
                                                        >
                                                            <div className="flex items-center gap-2 px-4 py-3">
                                                                <Icon
                                                                    name="clock"
                                                                    className="size-5"
                                                                />
                                                                <span className="text-sm font-medium text-gray-900">
                                                                    {t(
                                                                        'storybook.modal.versions.title'
                                                                    )}
                                                                </span>
                                                            </div>
                                                            <div className="max-h-80 overflow-y-auto bg-white">
                                                                {isLoadingVersions ? (
                                                                    <div className="px-4 py-6 text-center text-sm text-gray-400">
                                                                        {t(
                                                                            'storybook.modal.versions.loading'
                                                                        )}
                                                                    </div>
                                                                ) : versionEntries.length ===
                                                                  0 ? (
                                                                    <div className="px-4 py-6 text-center text-sm text-gray-400">
                                                                        {t(
                                                                            'storybook.modal.versions.empty'
                                                                        )}
                                                                    </div>
                                                                ) : (
                                                                    <div className="divide-y divide-gray-100">
                                                                        {versionEntries.map(
                                                                            (
                                                                                entry
                                                                            ) => (
                                                                                <button
                                                                                    key={
                                                                                        entry.id
                                                                                    }
                                                                                    type="button"
                                                                                    onClick={() => {
                                                                                        if (
                                                                                            !entry.is_current
                                                                                        ) {
                                                                                            handleEditModeVersionSelect(
                                                                                                entry.id
                                                                                            )
                                                                                            return
                                                                                        }
                                                                                        setIsVersionsOpen(
                                                                                            false
                                                                                        )
                                                                                    }}
                                                                                    className={cn(
                                                                                        'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
                                                                                        entry.is_current
                                                                                            ? 'bg-gray-50'
                                                                                            : 'hover:bg-gray-50'
                                                                                    )}
                                                                                >
                                                                                    <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
                                                                                        {entry.is_current && (
                                                                                            <svg
                                                                                                className="h-4 w-4 text-gray-900"
                                                                                                fill="none"
                                                                                                viewBox="0 0 24 24"
                                                                                                stroke="currentColor"
                                                                                                strokeWidth={
                                                                                                    2
                                                                                                }
                                                                                            >
                                                                                                <path
                                                                                                    strokeLinecap="round"
                                                                                                    strokeLinejoin="round"
                                                                                                    d="M5 13l4 4L19 7"
                                                                                                />
                                                                                            </svg>
                                                                                        )}
                                                                                    </div>
                                                                                    <div className="min-w-0 flex-1">
                                                                                        <div className="truncate text-sm text-gray-900">
                                                                                            {
                                                                                                title
                                                                                            }
                                                                                        </div>
                                                                                        <div className="text-xs text-gray-400">
                                                                                            {formatRelativeTime(
                                                                                                t,
                                                                                                entry.created_at
                                                                                            )}
                                                                                        </div>
                                                                                    </div>
                                                                                    <span className="flex-shrink-0 rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs font-medium text-gray-600">
                                                                                        {t(
                                                                                            'storybook.versionSelector.versionLabel',
                                                                                            {
                                                                                                version:
                                                                                                    entry.version
                                                                                            }
                                                                                        )}
                                                                                    </span>
                                                                                </button>
                                                                            )
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </PopoverContent>
                                                    </Popover>
                                                )}
                                            </div>

                                            <div className="h-10 w-10" />
                                        </div>
                                        <div className="chat-separator mx-auto !w-2/3 hidden md:block"></div>
                                    </div>

                                    <div className="hidden md:flex px-0 pt-0 pb-0 -mt-5 h-[69px]">
                                        <div className="flex w-full flex-col overflow-hidden border-b border-grey bg-white pt-5 dark:border-white/10 dark:bg-[#181e1c]">
                                            <div className="grid grid-cols-[1fr_auto] items-center -mt-1.5">
                                                <div className="flex h-12 items-center gap-2 px-4">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={
                                                            handleCancelEdit
                                                        }
                                                        className="h-7 w-7 text-black/60 hover:text-black hover:bg-black/5 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10"
                                                    >
                                                        <Icon
                                                            name="arrow-left-2"
                                                            className="size-4 fill-current"
                                                        />
                                                    </Button>
                                                    <span className="flex h-7 items-center rounded-full bg-[#bee6f0] px-3 text-xs font-semibold text-black whitespace-nowrap">
                                                        {t(
                                                            'storybook.modal.editMode.label'
                                                        )}
                                                    </span>
                                                    <Popover
                                                        open={isChangesOpen}
                                                        onOpenChange={
                                                            handleChangesOpenChange
                                                        }
                                                    >
                                                        <PopoverTrigger asChild>
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                className={cn(
                                                                    'h-7 rounded-full px-3 text-xs font-medium transition-colors whitespace-nowrap',
                                                                    hasUnsavedChanges
                                                                        ? 'bg-amber-200 text-amber-950 border border-amber-300 hover:bg-amber-300 dark:bg-amber-500/20 dark:text-amber-200 dark:border-amber-500/40 dark:hover:bg-amber-500/30'
                                                                        : 'bg-black/5 text-black/50 border border-black/10 hover:bg-black/10 dark:bg-white/10 dark:text-white/60 dark:border-white/20 dark:hover:bg-white/15'
                                                                )}
                                                            >
                                                                <span>
                                                                    {t(
                                                                        'storybook.modal.changes.unsavedCount',
                                                                        {
                                                                            count: totalChangesCount
                                                                        }
                                                                    )}
                                                                </span>
                                                            </Button>
                                                        </PopoverTrigger>
                                                        <PopoverContent
                                                            align="end"
                                                            className="w-80 rounded-xl border border-gray-200 bg-white dark:bg-white p-0 shadow-xl overflow-hidden text-black dark:text-black"
                                                        >
                                                            <div className="flex items-center gap-2 px-4 py-3">
                                                                <Icon
                                                                    name="change"
                                                                    className="size-5"
                                                                />
                                                                <span className="text-sm font-medium text-gray-900">
                                                                    {totalChangesCount ===
                                                                    0
                                                                        ? t(
                                                                              'storybook.modal.changes.none'
                                                                          )
                                                                        : t(
                                                                              'storybook.modal.changes.unsavedCount',
                                                                              {
                                                                                  count: totalChangesCount
                                                                              }
                                                                          )}
                                                                </span>
                                                            </div>
                                                            <div className="max-h-80 overflow-y-auto bg-white">
                                                                {changeItems.length ===
                                                                0 ? (
                                                                    <div className="px-4 py-6 text-center text-sm text-gray-400">
                                                                        {t(
                                                                            'storybook.modal.changes.pendingEmpty'
                                                                        )}
                                                                    </div>
                                                                ) : (
                                                                    <div className="divide-y divide-gray-100">
                                                                        {changeItems.map(
                                                                            (
                                                                                item
                                                                            ) => (
                                                                                <button
                                                                                    key={
                                                                                        item.key
                                                                                    }
                                                                                    type="button"
                                                                                    onClick={() =>
                                                                                        toggleChangeSelection(
                                                                                            item.key
                                                                                        )
                                                                                    }
                                                                                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50"
                                                                                >
                                                                                    <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
                                                                                        {selectedChangeKeys.has(
                                                                                            item.key
                                                                                        ) && (
                                                                                            <svg
                                                                                                className="h-4 w-4 text-gray-900"
                                                                                                fill="none"
                                                                                                viewBox="0 0 24 24"
                                                                                                stroke="currentColor"
                                                                                                strokeWidth={
                                                                                                    2
                                                                                                }
                                                                                            >
                                                                                                <path
                                                                                                    strokeLinecap="round"
                                                                                                    strokeLinejoin="round"
                                                                                                    d="M5 13l4 4L19 7"
                                                                                                />
                                                                                            </svg>
                                                                                        )}
                                                                                    </div>
                                                                                    <div className="min-w-0 flex-1">
                                                                                        <div className="truncate text-sm text-gray-900">
                                                                                            {t(
                                                                                                'storybook.modal.changes.pageLabel',
                                                                                                {
                                                                                                    page: item.pageNumber,
                                                                                                    label: item.label
                                                                                                }
                                                                                            )}
                                                                                        </div>
                                                                                        <div className="text-xs text-gray-400">
                                                                                            {formatRelativeTime(
                                                                                                t,
                                                                                                new Date(
                                                                                                    item.timestamp
                                                                                                ).toISOString()
                                                                                            )}
                                                                                        </div>
                                                                                    </div>
                                                                                </button>
                                                                            )
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2 border-t border-gray-100 px-4 py-3">
                                                                <Button
                                                                    size="sm"
                                                                    onClick={() => {
                                                                        setIsChangesOpen(
                                                                            false
                                                                        )
                                                                        void handleSaveSelectedChanges()
                                                                    }}
                                                                    disabled={
                                                                        selectedChangeKeys.size ===
                                                                            0 ||
                                                                        isSavingEdits
                                                                    }
                                                                    className="h-9 flex-1 text-sm bg-[#bee6f0] text-black hover:bg-[#a5d9e5] disabled:opacity-50"
                                                                >
                                                                    {isSavingEdits
                                                                        ? t(
                                                                              'common.saving'
                                                                          )
                                                                        : t(
                                                                              'common.save'
                                                                          )}
                                                                </Button>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    onClick={() => {
                                                                        handleClearAll()
                                                                        setSelectedChangeKeys(
                                                                            new Set()
                                                                        )
                                                                        setIsChangesOpen(
                                                                            false
                                                                        )
                                                                    }}
                                                                    disabled={
                                                                        !hasUnsavedChanges
                                                                    }
                                                                    className="h-9 flex-1 text-sm text-rose-500 hover:text-rose-600 hover:bg-rose-50 border border-transparent hover:border-rose-100"
                                                                >
                                                                    {t(
                                                                        'storybook.modal.actions.clear'
                                                                    )}
                                                                </Button>
                                                            </div>
                                                        </PopoverContent>
                                                    </Popover>
                                                    <div className="flex-1" />
                                                </div>
                                                <div className="flex items-center justify-end gap-2 px-4 py-2.5">
                                                    <div className="flex items-center gap-1 p-1">
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={handleUndo}
                                                            disabled={!canUndo}
                                                            className="h-8 w-8 text-black/60 hover:text-black hover:bg-black/5 disabled:opacity-20 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10"
                                                        >
                                                            <Icon
                                                                name="undo"
                                                                className="size-6 fill-current"
                                                            />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={handleRedo}
                                                            disabled={!canRedo}
                                                            className="h-8 w-8 text-black/60 hover:text-black hover:bg-black/5 disabled:opacity-20 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10"
                                                        >
                                                            <Icon
                                                                name="redo"
                                                                className="size-6 fill-current"
                                                            />
                                                        </Button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : showPublicHeader ? (
                                <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 py-3 bg-white dark:bg-charcoal rounded-t-2xl">
                                    <div className="flex gap-x-4 items-center flex-shrink-0">
                                        <Logo
                                            className="gap-x-[6px]"
                                            imageClassName={`${isSage ? '!h-6 md:!h-6' : 'size-6'} inline`}
                                            label="II-Agent"
                                            labelClassName="text-black dark:text-white text-sm font-semibold"
                                        />
                                        <Button
                                            onClick={() => navigate('/')}
                                            className="flex items-center gap-2 bg-sky-blue text-black font-medium px-4 py-2 rounded-full hover:opacity-90 transition-opacity"
                                        >
                                            <Icon
                                                name="ai-magic"
                                                className="size-5 stroke-black"
                                            />
                                            {t('presentations.createYourOwn')}
                                        </Button>
                                    </div>
                                    <h1 className="text-lg font-semibold text-black dark:text-white line-clamp-1 text-center">
                                        {title}
                                    </h1>
                                    <div className="flex items-center justify-end gap-2">
                                        <Button
                                            onClick={() =>
                                                setIsAutoPlayEnabled(
                                                    (prev) => !prev
                                                )
                                            }
                                            aria-pressed={isAutoPlayEnabled}
                                            className="flex items-center gap-2 rounded-full bg-[#a6ffff] px-4 py-2 text-sm font-semibold text-black transition-opacity hover:opacity-90"
                                        >
                                            <Icon
                                                name={
                                                    isAutoPlayEnabled
                                                        ? 'stop'
                                                        : 'play'
                                                }
                                                className={cn(
                                                    'size-5 text-black',
                                                    !isAutoPlayEnabled &&
                                                        'stroke-black'
                                                )}
                                            />
                                            {isAutoPlayEnabled
                                                ? t(
                                                      'storybook.viewer.stopAutoPlay'
                                                  )
                                                : t(
                                                      'storybook.viewer.autoPlay'
                                                  )}
                                        </Button>
                                        {!isMangaMode && (
                                            <Popover
                                                open={isVoicePromptOpen}
                                                onOpenChange={
                                                    handleVoicePromptOpenChange
                                                }
                                            >
                                                <PopoverAnchor asChild>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        aria-label="Voice"
                                                        onClick={
                                                            handleVoiceToggle
                                                        }
                                                        disabled={
                                                            isGeneratingVoice
                                                        }
                                                        className="relative h-10 w-10 hover:bg-black/5"
                                                    >
                                                        <Icon
                                                            name="voice"
                                                            className={cn(
                                                                'size-6',
                                                                isVoiceEnabled
                                                                    ? 'text-black dark:text-white'
                                                                    : 'text-gray-500 dark:text-gray-400'
                                                            )}
                                                        />
                                                    </Button>
                                                </PopoverAnchor>
                                                {renderVoiceOverPrompt()}
                                            </Popover>
                                        )}
                                        {!hasSeparateTextPages && (
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button
                                                        size="icon"
                                                        className="relative z-30 h-10 w-10 bg-black/10 text-black hover:bg-black/20 dark:bg-white/10 dark:text-white dark:hover:bg-white/20"
                                                    >
                                                        <Icon
                                                            name={
                                                                viewMode ===
                                                                'single'
                                                                    ? 'single-page'
                                                                    : 'double-page'
                                                            }
                                                            className="size-5 text-black dark:text-white"
                                                        />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent
                                                    align="end"
                                                    className="w-56"
                                                >
                                                    <DropdownMenuItem
                                                        onClick={() =>
                                                            setViewMode(
                                                                'single'
                                                            )
                                                        }
                                                        className={cn(
                                                            'gap-3',
                                                            viewMode ===
                                                                'single' &&
                                                                'bg-accent'
                                                        )}
                                                    >
                                                        <Icon
                                                            name="single-page"
                                                            className="size-4 text-black"
                                                        />
                                                        <span>
                                                            {t(
                                                                'storybook.viewer.viewSinglePage'
                                                            )}
                                                        </span>
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem
                                                        onClick={() =>
                                                            setViewMode(
                                                                'double'
                                                            )
                                                        }
                                                        className={cn(
                                                            'gap-3',
                                                            viewMode ===
                                                                'double' &&
                                                                'bg-accent'
                                                        )}
                                                    >
                                                        <Icon
                                                            name="double-page"
                                                            className="size-4 text-black"
                                                        />
                                                        <span>
                                                            {t(
                                                                'storybook.viewer.viewDoublePage'
                                                            )}
                                                        </span>
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                <div className="relative z-30 grid h-14 grid-cols-[1fr_auto_1fr] items-center">
                                    <div className="flex items-center gap-3 ml-4">
                                        <Button
                                            size="icon"
                                            onClick={closeModal}
                                            className="h-10 w-10"
                                        >
                                            <Icon
                                                name="close-2"
                                                className="size-5 fill-black/70 dark:fill-white/80"
                                            />
                                        </Button>
                                    </div>

                                    <div className="flex min-w-0 items-center justify-center gap-2 px-2 sm:px-4">
                                        <Icon
                                            name="image-2"
                                            className="size-4 flex-shrink-0 fill-black/50 dark:fill-white/50"
                                        />
                                        <span className="max-w-[200px] truncate text-sm font-medium sm:max-w-md">
                                            {title}
                                        </span>
                                        {versionLabel && (
                                            <Popover
                                                open={isVersionsOpen}
                                                onOpenChange={
                                                    handleVersionsOpenChange
                                                }
                                            >
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        size="sm"
                                                        className="h-7 px-2 rounded-full text-xs border border-sky-blue/40 bg-sky-blue/30 text-firefly hover:bg-sky-blue/40 dark:border-transparent dark:bg-[#bee6f0]/20 dark:text-[#bee6f0] dark:hover:bg-[#bee6f0]/30"
                                                    >
                                                        {versionLabel}
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent
                                                    align="center"
                                                    className="w-72 rounded-xl border border-gray-200 bg-white dark:bg-white p-0 shadow-xl overflow-hidden text-black dark:text-black"
                                                >
                                                    <div className="flex items-center gap-2 px-4 py-3">
                                                        <Icon
                                                            name="clock"
                                                            className="size-5"
                                                        />
                                                        <span className="text-sm font-medium text-gray-900">
                                                            {t(
                                                                'storybook.modal.versions.title'
                                                            )}
                                                        </span>
                                                    </div>
                                                    <div className="max-h-80 overflow-y-auto bg-white">
                                                        {isLoadingVersions ? (
                                                            <div className="px-4 py-6 text-center text-sm text-gray-400">
                                                                {t(
                                                                    'storybook.modal.versions.loading'
                                                                )}
                                                            </div>
                                                        ) : versionEntries.length ===
                                                          0 ? (
                                                            <div className="px-4 py-6 text-center text-sm text-gray-400">
                                                                {t(
                                                                    'storybook.modal.versions.empty'
                                                                )}
                                                            </div>
                                                        ) : (
                                                            <div className="divide-y divide-gray-100">
                                                                {versionEntries.map(
                                                                    (entry) => (
                                                                        <button
                                                                            key={
                                                                                entry.id
                                                                            }
                                                                            type="button"
                                                                            onClick={() => {
                                                                                // Close popover first to avoid DOM conflicts
                                                                                setIsVersionsOpen(
                                                                                    false
                                                                                )
                                                                                // Delay version switch to allow popover to close
                                                                                if (
                                                                                    !entry.is_current
                                                                                ) {
                                                                                    setTimeout(
                                                                                        () => {
                                                                                            switchToVersion(
                                                                                                entry.id
                                                                                            )
                                                                                        },
                                                                                        100
                                                                                    )
                                                                                }
                                                                            }}
                                                                            className={cn(
                                                                                'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
                                                                                entry.is_current
                                                                                    ? 'bg-gray-50'
                                                                                    : 'hover:bg-gray-50'
                                                                            )}
                                                                        >
                                                                            <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
                                                                                {entry.is_current && (
                                                                                    <svg
                                                                                        className="h-4 w-4 text-gray-900"
                                                                                        fill="none"
                                                                                        viewBox="0 0 24 24"
                                                                                        stroke="currentColor"
                                                                                        strokeWidth={
                                                                                            2
                                                                                        }
                                                                                    >
                                                                                        <path
                                                                                            strokeLinecap="round"
                                                                                            strokeLinejoin="round"
                                                                                            d="M5 13l4 4L19 7"
                                                                                        />
                                                                                    </svg>
                                                                                )}
                                                                            </div>
                                                                            <div className="min-w-0 flex-1">
                                                                                <div className="truncate text-sm text-gray-900">
                                                                                    {
                                                                                        title
                                                                                    }
                                                                                </div>
                                                                                <div className="text-xs text-gray-400">
                                                                                    {formatRelativeTime(
                                                                                        t,
                                                                                        entry.created_at
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                            <span className="flex-shrink-0 rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs font-medium text-gray-600">
                                                                                {t(
                                                                                    'storybook.versionSelector.versionLabel',
                                                                                    {
                                                                                        version:
                                                                                            entry.version
                                                                                    }
                                                                                )}
                                                                            </span>
                                                                        </button>
                                                                    )
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>
                                                </PopoverContent>
                                            </Popover>
                                        )}
                                    </div>

                                    <div className="relative z-30 flex items-center justify-end gap-2">
                                        {/* Share Button - Hidden in edit mode */}
                                        {!isEditMode && !isShareMode && (
                                            <Button
                                                variant="outline"
                                                onClick={() => {
                                                    if (
                                                        !currentStorybook?.sessionId
                                                    ) {
                                                        toast.error(
                                                            t(
                                                                'storybook.modal.toasts.noSession'
                                                            )
                                                        )
                                                        return
                                                    }
                                                    setIsShareOpen(true)
                                                }}
                                                className="group hidden h-9 gap-2 rounded-full border border-firefly/30 bg-transparent px-4 text-firefly transition hover:bg-firefly/10 sm:flex dark:border-[#bee6f0] dark:text-[#bee6f0] dark:hover:bg-[#bee6f0] dark:hover:text-white"
                                            >
                                                <Icon
                                                    name="share-2"
                                                    className="size-3.5 fill-firefly group-hover:fill-firefly dark:fill-[#bee6f0] dark:group-hover:fill-white"
                                                />
                                                <span className="text-xs font-medium fill-[#bee6f0]">
                                                    {t('common.share')}
                                                </span>
                                            </Button>
                                        )}

                                        {/* Edit Button - Hidden in edit mode */}
                                        {!isEditMode &&
                                            !isShareMode &&
                                            useNewFormat &&
                                            currentStorybook && (
                                                <Button
                                                    variant="outline"
                                                    onClick={() => {
                                                        enterEditMode(
                                                            currentStorybook.id,
                                                            pages[currentPage]
                                                                ?.pageNumber ||
                                                                1
                                                        )
                                                    }}
                                                    className="group hidden h-9 gap-2 rounded-full border-none !bg-firefly/10 px-4 text-firefly transition hover:!bg-firefly/20 sm:flex !m-0 dark:!bg-[#293231] dark:text-[#bee6f0] dark:hover:!bg-[#bee6f0] dark:hover:text-white"
                                                >
                                                    <Icon
                                                        name="edit"
                                                        className="size-3.5 fill-firefly group-hover:fill-firefly dark:fill-[#bee6f0] dark:group-hover:fill-white"
                                                    />
                                                    <span className="text-xs font-medium">
                                                        {t(
                                                            'storybook.modal.editMode.label'
                                                        )}
                                                    </span>
                                                </Button>
                                            )}

                                        <Button
                                            onClick={() =>
                                                setIsAutoPlayEnabled(
                                                    (prev) => !prev
                                                )
                                            }
                                            aria-pressed={isAutoPlayEnabled}
                                            className="flex items-center gap-2 rounded-full bg-[#a6ffff] px-4 py-2 text-sm font-semibold text-black transition-opacity hover:opacity-90"
                                        >
                                            <Icon
                                                name={
                                                    isAutoPlayEnabled
                                                        ? 'stop'
                                                        : 'play'
                                                }
                                                className={cn(
                                                    'size-5 text-black',
                                                    !isAutoPlayEnabled &&
                                                        'stroke-black'
                                                )}
                                            />
                                            {isAutoPlayEnabled
                                                ? t(
                                                      'storybook.viewer.stopAutoPlay'
                                                  )
                                                : t(
                                                      'storybook.viewer.autoPlay'
                                                  )}
                                        </Button>
                                        {!isMangaMode && (
                                            <Popover
                                                open={isVoicePromptOpen}
                                                onOpenChange={
                                                    handleVoicePromptOpenChange
                                                }
                                            >
                                                <PopoverAnchor asChild>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        aria-label="Voice"
                                                        onClick={
                                                            handleVoiceToggle
                                                        }
                                                        disabled={
                                                            isGeneratingVoice
                                                        }
                                                        className="relative z-30 h-10 w-10 hover:bg-transparent"
                                                    >
                                                        <Icon
                                                            name="voice"
                                                            className={cn(
                                                                'size-6',
                                                                isVoiceEnabled
                                                                    ? 'text-black dark:text-white'
                                                                    : 'text-gray-500 dark:text-gray-400'
                                                            )}
                                                        />
                                                    </Button>
                                                </PopoverAnchor>
                                                {renderVoiceOverPrompt()}
                                            </Popover>
                                        )}

                                        {/* View Mode Dropdown - Hidden in edit mode and for separate_page storybooks */}
                                        {!isEditMode &&
                                            !hasSeparateTextPages && (
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger
                                                        asChild
                                                    >
                                                        <Button
                                                            size="icon"
                                                            className="relative z-30 h-10 w-10"
                                                        >
                                                            <Icon
                                                                name={
                                                                    viewMode ===
                                                                    'single'
                                                                        ? 'single-page'
                                                                        : 'double-page'
                                                                }
                                                                className="size-5 text-black dark:text-white"
                                                            />
                                                        </Button>
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent
                                                        align="end"
                                                        className="w-56"
                                                    >
                                                        <DropdownMenuItem
                                                            onClick={() =>
                                                                setViewMode(
                                                                    'single'
                                                                )
                                                            }
                                                            className={cn(
                                                                'gap-3',
                                                                viewMode ===
                                                                    'single' &&
                                                                    'bg-accent'
                                                            )}
                                                        >
                                                            <Icon
                                                                name="single-page"
                                                                className="size-4 text-black"
                                                            />
                                                            <span>
                                                                {t(
                                                                    'storybook.viewer.viewSinglePage'
                                                                )}
                                                            </span>
                                                        </DropdownMenuItem>
                                                        <DropdownMenuItem
                                                            onClick={() =>
                                                                setViewMode(
                                                                    'double'
                                                                )
                                                            }
                                                            className={cn(
                                                                'gap-3',
                                                                viewMode ===
                                                                    'double' &&
                                                                    'bg-accent'
                                                            )}
                                                        >
                                                            <Icon
                                                                name="double-page"
                                                                className="size-4 text-black"
                                                            />
                                                            <span>
                                                                {t(
                                                                    'storybook.viewer.viewDoublePage'
                                                                )}
                                                            </span>
                                                        </DropdownMenuItem>
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            )}

                                        {!isEditMode && (
                                            <Popover>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        className="relative z-30 mr-4 h-10 w-10 hover:bg-transparent"
                                                    >
                                                        <Icon
                                                            name="download"
                                                            className="size-5 fill-black dark:fill-white"
                                                        />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent
                                                    className="w-64 border-none bg-white p-4 shadow-btn rounded-xl dark:bg-white dark:text-black"
                                                    align="end"
                                                >
                                                    <div className="flex gap-2 mb-4">
                                                        <button
                                                            onClick={() =>
                                                                setDownloadFormat(
                                                                    'pdf'
                                                                )
                                                            }
                                                            className={cn(
                                                                'flex-1 py-2 rounded-lg text-sm font-medium transition-colors',
                                                                downloadFormat ===
                                                                    'pdf'
                                                                    ? 'bg-[#bee6f0] text-black'
                                                                    : 'bg-[#ebf7fc] text-black/60 hover:bg-[#bee6f0]/50'
                                                            )}
                                                        >
                                                            {t(
                                                                'storybook.viewer.download.pdf'
                                                            )}
                                                        </button>
                                                        <button
                                                            onClick={() =>
                                                                setDownloadFormat(
                                                                    'png'
                                                                )
                                                            }
                                                            className={cn(
                                                                'flex-1 py-2 rounded-lg text-sm font-medium transition-colors',
                                                                downloadFormat ===
                                                                    'png'
                                                                    ? 'bg-[#bee6f0] text-black'
                                                                    : 'bg-[#ebf7fc] text-black/60 hover:bg-[#bee6f0]/50'
                                                            )}
                                                        >
                                                            {t(
                                                                'storybook.viewer.download.png'
                                                            )}
                                                        </button>
                                                    </div>

                                                    <div className="space-y-2">
                                                        <button
                                                            className={cn(
                                                                'w-full flex items-center gap-3 p-2 hover:bg-gray-100 rounded-lg text-sm transition-colors text-left text-black',
                                                                isDownloading &&
                                                                    'cursor-not-allowed opacity-70'
                                                            )}
                                                            onClick={() =>
                                                                handleDownload(
                                                                    'current'
                                                                )
                                                            }
                                                            disabled={
                                                                isDownloading
                                                            }
                                                        >
                                                            <Icon
                                                                name={
                                                                    isCurrentDownloading
                                                                        ? 'loader'
                                                                        : 'download'
                                                                }
                                                                className={cn(
                                                                    'size-4',
                                                                    isCurrentDownloading
                                                                        ? 'text-black animate-spin'
                                                                        : 'fill-black'
                                                                )}
                                                            />
                                                            <span>
                                                                {isCurrentDownloading
                                                                    ? t(
                                                                          'storybook.viewer.download.preparing'
                                                                      )
                                                                    : t(
                                                                          'storybook.viewer.download.current'
                                                                      )}
                                                            </span>
                                                        </button>
                                                        <button
                                                            className={cn(
                                                                'w-full flex items-center gap-3 p-2 hover:bg-gray-100 rounded-lg text-sm transition-colors text-left text-black',
                                                                isDownloading &&
                                                                    'cursor-not-allowed opacity-70'
                                                            )}
                                                            onClick={() =>
                                                                handleDownload(
                                                                    'all'
                                                                )
                                                            }
                                                            disabled={
                                                                isDownloading
                                                            }
                                                        >
                                                            <Icon
                                                                name={
                                                                    isAllDownloading
                                                                        ? 'loader'
                                                                        : 'download'
                                                                }
                                                                className={cn(
                                                                    'size-4',
                                                                    isAllDownloading
                                                                        ? 'text-black animate-spin'
                                                                        : 'fill-black'
                                                                )}
                                                            />
                                                            <span>
                                                                {isAllDownloading
                                                                    ? t(
                                                                          'storybook.viewer.download.preparing'
                                                                      )
                                                                    : t(
                                                                          'storybook.viewer.download.all'
                                                                      )}
                                                            </span>
                                                        </button>
                                                    </div>
                                                </PopoverContent>
                                            </Popover>
                                        )}
                                    </div>
                                </div>
                            )}

                            {!isEditMode && (
                                <div className="chat-separator mx-auto !w-2/3 hidden md:block"></div>
                            )}

                            {/* Main Content */}
                            {isEditMode && currentStorybook ? (
                                /* Edit Mode View - Single page with Design Inspector on right */
                                <div className="grid flex-1 min-h-0 md:grid-cols-[minmax(0,1fr)_28rem] overflow-hidden">
                                    <div className="flex flex-1 flex-col gap-3 px-3 pb-3 pt-2 sm:px-4 sm:pb-4 sm:pt-3 overflow-hidden">
                                        {/* Edit Mode Toolbar (mobile) */}
                                        <div className="flex md:hidden items-center justify-between px-3 py-2 bg-grey-3 rounded-xl flex-shrink-0 dark:bg-[#1e2624]">
                                            <div className="flex items-center gap-3">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={handleCancelEdit}
                                                    disabled={isSavingEdits}
                                                    className="h-8 gap-2 text-black/60 hover:text-black hover:bg-black/5 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10"
                                                >
                                                    <Icon
                                                        name="arrow-left-2"
                                                        className="size-4 fill-current"
                                                    />
                                                    {t(
                                                        'storybook.modal.actions.back'
                                                    )}
                                                </Button>
                                                <div className="h-4 w-px bg-white/20" />
                                                <span className="text-sm text-black/60 dark:text-white/70">
                                                    {editPageLabel}
                                                </span>
                                                {hasUnsavedChanges && (
                                                    <span className="text-xs px-2 py-0.5 bg-amber-500/20 text-amber-400 rounded">
                                                        {t(
                                                            'storybook.modal.changes.unsavedCount',
                                                            {
                                                                count: totalChangesCount
                                                            }
                                                        )}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={handleCancelEdit}
                                                    disabled={isSavingEdits}
                                                    className="h-8 text-black/60 border-grey/60 hover:bg-black/5 dark:text-white/70 dark:border-white/20 dark:hover:bg-white/10"
                                                >
                                                    {t('common.cancel')}
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    onClick={handleSaveEdits}
                                                    disabled={
                                                        !hasUnsavedChanges ||
                                                        isSavingEdits
                                                    }
                                                    className="h-8 bg-[#bee6f0] text-black hover:bg-[#a5d9e5] disabled:opacity-50"
                                                >
                                                    {isSavingEdits
                                                        ? t('common.saving')
                                                        : t(
                                                              'storybook.modal.actions.saveChanges'
                                                          )}
                                                </Button>
                                            </div>
                                        </div>

                                        {/* Edit Mode Content: Preview on left */}
                                        <div className="flex flex-1 flex-col gap-3 min-w-0 overflow-hidden">
                                            <div className="relative flex-1 overflow-hidden rounded-xl bg-background">
                                                {/* Navigation Arrows */}
                                                <button
                                                    onClick={() => {
                                                        const current =
                                                            currentEditPage || 1
                                                        if (
                                                            hasSeparateTextPages
                                                        ) {
                                                            // Page 1 is cover, pairs start from 2-3, 4-5, etc.
                                                            if (current === 2) {
                                                                setCurrentEditPage(
                                                                    1
                                                                )
                                                            } else if (
                                                                current > 2
                                                            ) {
                                                                setCurrentEditPage(
                                                                    current - 2
                                                                )
                                                            }
                                                        } else {
                                                            if (current > 1) {
                                                                setCurrentEditPage(
                                                                    current - 1
                                                                )
                                                            }
                                                        }
                                                    }}
                                                    disabled={
                                                        (currentEditPage ||
                                                            1) <= 1
                                                    }
                                                    className="absolute left-3 top-1/2 z-20 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-[#c6ebf7] transition hover:scale-105 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/40"
                                                >
                                                    <Icon
                                                        name="arrow-left-2"
                                                        className="size-5 fill-[#0f1511]"
                                                    />
                                                </button>

                                                <button
                                                    onClick={() => {
                                                        const current =
                                                            currentEditPage || 1
                                                        if (
                                                            hasSeparateTextPages
                                                        ) {
                                                            // Page 1 is cover, pairs start from 2-3, 4-5, etc.
                                                            if (current === 1) {
                                                                setCurrentEditPage(
                                                                    2
                                                                )
                                                            } else if (
                                                                current + 2 <=
                                                                pages.length
                                                            ) {
                                                                setCurrentEditPage(
                                                                    current + 2
                                                                )
                                                            }
                                                        } else {
                                                            if (
                                                                current <
                                                                pages.length
                                                            ) {
                                                                setCurrentEditPage(
                                                                    current + 1
                                                                )
                                                            }
                                                        }
                                                    }}
                                                    disabled={
                                                        hasSeparateTextPages
                                                            ? (currentEditPage ||
                                                                  1) >=
                                                              pages.length - 1
                                                            : (currentEditPage ||
                                                                  1) >=
                                                              pages.length
                                                    }
                                                    className="absolute right-3 top-1/2 z-20 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-[#c6ebf7] transition hover:scale-105 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/40"
                                                >
                                                    <Icon
                                                        name="arrow-right-2"
                                                        className="size-5 fill-[#0f1511]"
                                                    />
                                                </button>

                                                {/* Page Editor Wrapper - Show side by side for separate mode (except cover) */}
                                                {hasSeparateTextPages &&
                                                (currentEditPage || 1) >= 2 ? (
                                                    <div className="flex h-full w-full gap-0 p-2">
                                                        {/* Image Page */}
                                                        <StorybookEditWrapper
                                                            storybookId={
                                                                currentStorybook.id
                                                            }
                                                            pageNumber={
                                                                currentEditPage ||
                                                                1
                                                            }
                                                            className="h-full flex-1"
                                                            onElementSelect={handleElementSelect(
                                                                currentEditPage ||
                                                                    1
                                                            )}
                                                            onUndoRequest={
                                                                handleUndo
                                                            }
                                                            onRedoRequest={
                                                                handleRedo
                                                            }
                                                        />
                                                        {/* Text Page */}
                                                        {(currentEditPage ||
                                                            1) <
                                                            pages.length && (
                                                            <StorybookEditWrapper
                                                                storybookId={
                                                                    currentStorybook.id
                                                                }
                                                                pageNumber={
                                                                    (currentEditPage ||
                                                                        1) + 1
                                                                }
                                                                className="h-full flex-1"
                                                                onElementSelect={handleElementSelect(
                                                                    (currentEditPage ||
                                                                        1) + 1
                                                                )}
                                                                onUndoRequest={
                                                                    handleUndo
                                                                }
                                                                onRedoRequest={
                                                                    handleRedo
                                                                }
                                                            />
                                                        )}
                                                    </div>
                                                ) : (
                                                    <StorybookEditWrapper
                                                        storybookId={
                                                            currentStorybook.id
                                                        }
                                                        pageNumber={
                                                            currentEditPage || 1
                                                        }
                                                        className="h-full w-full"
                                                        onElementSelect={handleElementSelect(
                                                            currentEditPage || 1
                                                        )}
                                                        onUndoRequest={
                                                            handleUndo
                                                        }
                                                        onRedoRequest={
                                                            handleRedo
                                                        }
                                                    />
                                                )}
                                                {isRegeneratingImage && (
                                                    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/15 backdrop-blur-sm">
                                                        <Shimmer
                                                            className="text-xl font-medium"
                                                            duration={1}
                                                        >
                                                            {t(
                                                                'storybook.modal.status.generating'
                                                            )}
                                                        </Shimmer>
                                                    </div>
                                                )}
                                                {isSavingEdits && (
                                                    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/15 backdrop-blur-sm">
                                                        <Shimmer
                                                            className="text-xl font-medium"
                                                            duration={1}
                                                        >
                                                            {t(
                                                                'storybook.modal.status.generating'
                                                            )}
                                                        </Shimmer>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Page Thumbnails for Edit Mode */}
                                            <div className="rounded-xl px-3 py-2 sm:px-4 sm:py-3 flex justify-center">
                                                <div
                                                    ref={editThumbsRef}
                                                    className="scrollbar-hide flex items-center gap-3 overflow-x-auto pb-1"
                                                >
                                                    {hasSeparateTextPages
                                                        ? // Separate mode: cover alone, then paired thumbnails (2-3, 4-5, etc.)
                                                          (() => {
                                                              const thumbnails =
                                                                  []
                                                              // Cover page (page 1)
                                                              const coverPage =
                                                                  pages[0]
                                                              if (coverPage) {
                                                                  const isCoverActive =
                                                                      currentEditPage ===
                                                                      1
                                                                  const coverHasChanges =
                                                                      getPageHasChanges(
                                                                          1
                                                                      )
                                                                  thumbnails.push(
                                                                      <div
                                                                          key="cover"
                                                                          data-thumb-page={
                                                                              coverPage.pageNumber
                                                                          }
                                                                          className="relative"
                                                                      >
                                                                          {useNewFormat &&
                                                                          coverPage.htmlContent ? (
                                                                              <StorybookPageThumbnail
                                                                                  page={
                                                                                      coverPage
                                                                                  }
                                                                                  overrideImageUrl={
                                                                                      getImageOverrideForPage(
                                                                                          coverPage.pageNumber
                                                                                      ) ??
                                                                                      undefined
                                                                                  }
                                                                                  isActive={
                                                                                      isCoverActive
                                                                                  }
                                                                                  onClick={() =>
                                                                                      setCurrentEditPage(
                                                                                          1
                                                                                      )
                                                                                  }
                                                                              />
                                                                          ) : (
                                                                              <button
                                                                                  onClick={() =>
                                                                                      setCurrentEditPage(
                                                                                          1
                                                                                      )
                                                                                  }
                                                                                  className={cn(
                                                                                      'relative h-[4.5rem] w-[3.5rem] flex-shrink-0 overflow-hidden rounded-lg border transition-all duration-200 sm:h-20 sm:w-16',
                                                                                      isCoverActive
                                                                                          ? 'border-[#bfefff]'
                                                                                          : 'border-black/10 opacity-60 hover:opacity-100 dark:border-white/5'
                                                                                  )}
                                                                              >
                                                                                  <img
                                                                                      src={
                                                                                          getImageOverrideForPage(
                                                                                              coverPage.pageNumber
                                                                                          ) ||
                                                                                          coverPage.imageUrl ||
                                                                                          ''
                                                                                      }
                                                                                      alt={t(
                                                                                          'storybook.viewer.pageAlt',
                                                                                          {
                                                                                              page: 1
                                                                                          }
                                                                                      )}
                                                                                      className="h-full w-full object-contain rounded"
                                                                                  />
                                                                              </button>
                                                                          )}
                                                                          {coverHasChanges && (
                                                                              <span className="absolute top-0.5 right-0.5 h-2 w-2 rounded-full bg-amber-400 ring-1 ring-black/20" />
                                                                          )}
                                                                      </div>
                                                                  )
                                                              }
                                                              // Pairs starting from page 2 (indices 1, 2), (3, 4), etc.
                                                              for (
                                                                  let i = 1;
                                                                  i <
                                                                  pages.length;
                                                                  i += 2
                                                              ) {
                                                                  const imagePage =
                                                                      pages[i]
                                                                  const textPage =
                                                                      pages[
                                                                          i + 1
                                                                      ]
                                                                  if (
                                                                      !imagePage
                                                                  )
                                                                      continue
                                                                  const pairHasChanges =
                                                                      getPageHasChanges(
                                                                          imagePage.pageNumber
                                                                      ) ||
                                                                      (textPage &&
                                                                          getPageHasChanges(
                                                                              textPage.pageNumber
                                                                          ))
                                                                  // Check if either page in the pair is active
                                                                  const isPairActive =
                                                                      currentEditPage ===
                                                                          imagePage.pageNumber ||
                                                                      (textPage &&
                                                                          currentEditPage ===
                                                                              textPage.pageNumber)
                                                                  thumbnails.push(
                                                                      <div
                                                                          key={
                                                                              imagePage.id
                                                                          }
                                                                          data-thumb-page={
                                                                              imagePage.pageNumber
                                                                          }
                                                                          className="relative flex gap-1.5 transition-all duration-200"
                                                                      >
                                                                          {/* Image page thumbnail */}
                                                                          {useNewFormat &&
                                                                          imagePage.htmlContent ? (
                                                                              <StorybookPageThumbnail
                                                                                  page={
                                                                                      imagePage
                                                                                  }
                                                                                  overrideImageUrl={
                                                                                      getImageOverrideForPage(
                                                                                          imagePage.pageNumber
                                                                                      ) ??
                                                                                      undefined
                                                                                  }
                                                                                  isActive={
                                                                                      isPairActive
                                                                                  }
                                                                                  onClick={() =>
                                                                                      setCurrentEditPage(
                                                                                          imagePage.pageNumber
                                                                                      )
                                                                                  }
                                                                              />
                                                                          ) : (
                                                                              <button
                                                                                  onClick={() =>
                                                                                      setCurrentEditPage(
                                                                                          imagePage.pageNumber
                                                                                      )
                                                                                  }
                                                                                  className={cn(
                                                                                      'relative h-[4.5rem] w-[3.5rem] flex-shrink-0 overflow-hidden rounded-lg border transition-all duration-200 sm:h-20 sm:w-16',
                                                                                      isPairActive
                                                                                          ? 'border-[#bfefff]'
                                                                                          : 'border-black/10 opacity-60 hover:opacity-100 dark:border-white/5'
                                                                                  )}
                                                                              >
                                                                                  <img
                                                                                      src={
                                                                                          getImageOverrideForPage(
                                                                                              imagePage.pageNumber
                                                                                          ) ||
                                                                                          imagePage.imageUrl ||
                                                                                          ''
                                                                                      }
                                                                                      alt={t(
                                                                                          'storybook.viewer.pageAlt',
                                                                                          {
                                                                                              page: imagePage.pageNumber
                                                                                          }
                                                                                      )}
                                                                                      className="h-full w-full object-contain rounded"
                                                                                  />
                                                                              </button>
                                                                          )}
                                                                          {/* Text page thumbnail */}
                                                                          {textPage &&
                                                                              (useNewFormat &&
                                                                              textPage.htmlContent ? (
                                                                                  <StorybookPageThumbnail
                                                                                      page={
                                                                                          textPage
                                                                                      }
                                                                                      overrideImageUrl={
                                                                                          getImageOverrideForPage(
                                                                                              textPage.pageNumber
                                                                                          ) ??
                                                                                          undefined
                                                                                      }
                                                                                      isActive={
                                                                                          isPairActive
                                                                                      }
                                                                                      onClick={() =>
                                                                                          setCurrentEditPage(
                                                                                              imagePage.pageNumber
                                                                                          )
                                                                                      }
                                                                                  />
                                                                              ) : (
                                                                                  <button
                                                                                      onClick={() =>
                                                                                          setCurrentEditPage(
                                                                                              imagePage.pageNumber
                                                                                          )
                                                                                      }
                                                                                      className={cn(
                                                                                          'relative h-[4.5rem] w-[3.5rem] flex-shrink-0 overflow-hidden rounded-lg border transition-all duration-200 sm:h-20 sm:w-16',
                                                                                          isPairActive
                                                                                              ? 'border-[#bfefff]'
                                                                                              : 'border-black/10 opacity-60 hover:opacity-100 dark:border-white/5'
                                                                                      )}
                                                                                  >
                                                                                      <img
                                                                                          src={
                                                                                              getImageOverrideForPage(
                                                                                                  textPage.pageNumber
                                                                                              ) ||
                                                                                              textPage.imageUrl ||
                                                                                              ''
                                                                                          }
                                                                                          alt={t(
                                                                                              'storybook.viewer.pageAlt',
                                                                                              {
                                                                                                  page: textPage.pageNumber
                                                                                              }
                                                                                          )}
                                                                                          className="h-full w-full object-contain rounded"
                                                                                      />
                                                                                  </button>
                                                                              ))}
                                                                          {/* Changes indicator */}
                                                                          {pairHasChanges && (
                                                                              <span className="absolute top-0.5 right-0.5 h-2 w-2 rounded-full bg-amber-400 ring-1 ring-black/20" />
                                                                          )}
                                                                      </div>
                                                                  )
                                                              }
                                                              return thumbnails
                                                          })()
                                                        : // Normal mode: show individual thumbnails
                                                          pages.map(
                                                              (page, index) => {
                                                                  const isActive =
                                                                      page.pageNumber ===
                                                                      currentEditPage
                                                                  const pageHasChanges =
                                                                      getPageHasChanges(
                                                                          page.pageNumber
                                                                      )

                                                                  // For new format with HTML, use StorybookPageThumbnail
                                                                  if (
                                                                      useNewFormat &&
                                                                      page.htmlContent
                                                                  ) {
                                                                      return (
                                                                          <div
                                                                              key={
                                                                                  page.id
                                                                              }
                                                                              data-thumb-page={
                                                                                  page.pageNumber
                                                                              }
                                                                              className="relative"
                                                                          >
                                                                              <StorybookPageThumbnail
                                                                                  page={
                                                                                      page
                                                                                  }
                                                                                  overrideImageUrl={
                                                                                      getImageOverrideForPage(
                                                                                          page.pageNumber
                                                                                      ) ??
                                                                                      undefined
                                                                                  }
                                                                                  isActive={
                                                                                      isActive
                                                                                  }
                                                                                  onClick={() =>
                                                                                      setCurrentEditPage(
                                                                                          page.pageNumber
                                                                                      )
                                                                                  }
                                                                              />
                                                                              {pageHasChanges && (
                                                                                  <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-amber-400 ring-1 ring-black/20" />
                                                                              )}
                                                                          </div>
                                                                      )
                                                                  }

                                                                  // Legacy image thumbnail
                                                                  return (
                                                                      <button
                                                                          key={
                                                                              page.id
                                                                          }
                                                                          data-thumb-page={
                                                                              page.pageNumber
                                                                          }
                                                                          onClick={() =>
                                                                              setCurrentEditPage(
                                                                                  page.pageNumber
                                                                              )
                                                                          }
                                                                          className={cn(
                                                                              'relative h-[4.5rem] w-[3.5rem] flex-shrink-0 overflow-hidden rounded-lg border transition-all duration-200 sm:h-20 sm:w-16',
                                                                              isActive
                                                                                  ? 'border-[#bfefff]'
                                                                                  : 'border-black/10 opacity-60 hover:opacity-100 dark:border-white/5'
                                                                          )}
                                                                      >
                                                                          <img
                                                                              src={
                                                                                  getImageOverrideForPage(
                                                                                      page.pageNumber
                                                                                  ) ||
                                                                                  page.imageUrl ||
                                                                                  ''
                                                                              }
                                                                              alt={t(
                                                                                  'storybook.viewer.pageAlt',
                                                                                  {
                                                                                      page:
                                                                                          index +
                                                                                          1
                                                                                  }
                                                                              )}
                                                                              className="h-full w-full object-contain"
                                                                          />
                                                                          <span className="absolute bottom-1 right-1 rounded-full bg-black/60 px-2 text-[10px] font-semibold text-white">
                                                                              {index +
                                                                                  1}
                                                                          </span>
                                                                          {pageHasChanges && (
                                                                              <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-amber-400 ring-1 ring-black/20" />
                                                                          )}
                                                                      </button>
                                                                  )
                                                              }
                                                          )}
                                                    {/*<button className="flex h-[4.5rem] w-[3.5rem] flex-shrink-0 flex-col items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white transition hover:bg-white/10 sm:h-20 sm:w-16">*/}
                                                    {/*    <Icon*/}
                                                    {/*        name="plus"*/}
                                                    {/*        className="size-4 fill-white/80"*/}
                                                    {/*    />*/}
                                                    {/*    <span className="mt-1 text-[9px] font-semibold uppercase text-white/70">*/}
                                                    {/*        {t(*/}
                                                    {/*            'storybook.viewer.add'*/}
                                                    {/*        )}*/}
                                                    {/*    </span>*/}
                                                    {/*</button>*/}
                                                </div>
                                            </div>

                                            {/* Chat Input at Bottom */}
                                            <div className="flex justify-center rounded-xl px-3 py-2 sm:px-4 sm:py-3">
                                                <div
                                                    className={cn(
                                                        'relative flex w-full max-w-4xl items-stretch gap-3 rounded-2xl px-3 py-3 transition-colors sm:px-4',
                                                        isDescribeDisabled
                                                            ? 'border border-grey bg-grey-3 dark:border-white/10 dark:bg-[#1d2120]'
                                                            : 'border-2 border-sky-blue bg-white dark:border-[#bfefff] dark:bg-[#151716]'
                                                    )}
                                                >
                                                    <input
                                                        ref={
                                                            referenceFileInputRef
                                                        }
                                                        type="file"
                                                        accept="image/*"
                                                        onChange={
                                                            handleReferenceUploadChange
                                                        }
                                                        className="hidden"
                                                    />
                                                    <div className="flex min-w-0 flex-1 flex-col gap-2">
                                                        {referenceImageUrl && (
                                                            <div className="flex items-start">
                                                                <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg border border-grey bg-grey-3 dark:border-white/10 dark:bg-white/5">
                                                                    <img
                                                                        src={
                                                                            referenceImageUrl
                                                                        }
                                                                        alt={t(
                                                                            'storybook.modal.reference.previewAlt'
                                                                        )}
                                                                        className="h-full w-full object-cover"
                                                                    />
                                                                    <button
                                                                        type="button"
                                                                        onClick={
                                                                            clearReferenceImage
                                                                        }
                                                                        aria-label={t(
                                                                            'storybook.modal.reference.removeLabel'
                                                                        )}
                                                                        className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/70 text-white/80 shadow-sm transition hover:bg-black/80"
                                                                    >
                                                                        <Icon
                                                                            name="close"
                                                                            className="size-3 fill-current"
                                                                        />
                                                                        <span className="sr-only">
                                                                            {t(
                                                                                'storybook.modal.reference.removeLabel'
                                                                            )}
                                                                        </span>
                                                                    </button>
                                                                </div>
                                                                {referenceImageName && (
                                                                    <span className="sr-only">
                                                                        {
                                                                            referenceImageName
                                                                        }
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}
                                                        <input
                                                            type="text"
                                                            value={description}
                                                            onChange={(e) =>
                                                                setDescription(
                                                                    e.target
                                                                        .value
                                                                )
                                                            }
                                                            onKeyDown={(
                                                                event
                                                            ) => {
                                                                if (
                                                                    event.key ===
                                                                        'Enter' &&
                                                                    !event.shiftKey
                                                                ) {
                                                                    event.preventDefault()
                                                                    handleRegenerateImage()
                                                                }
                                                            }}
                                                            placeholder={t(
                                                                'storybook.viewer.describeToEdit'
                                                            )}
                                                            disabled={
                                                                isDescribeDisabled
                                                            }
                                                            className={cn(
                                                                'h-9 min-w-0 w-full bg-transparent px-1 text-sm outline-none',
                                                                isDescribeDisabled
                                                                    ? 'cursor-not-allowed text-black/40 placeholder-black/30 dark:text-white/40 dark:placeholder-white/20'
                                                                    : 'text-black placeholder-black/40 dark:text-white dark:placeholder-white/40'
                                                            )}
                                                        />
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={
                                                                handleReferenceUploadClick
                                                            }
                                                            disabled={
                                                                isAttachDisabled
                                                            }
                                                            className={cn(
                                                                'flex h-9 w-9 items-center justify-center rounded-full border transition',
                                                                isAttachDisabled
                                                                    ? 'cursor-not-allowed border-grey bg-black/5 text-black/40 dark:border-white/10 dark:bg-white/10 dark:text-white/40'
                                                                    : 'border-grey bg-[#bee6f0] text-black dark:border-white/10'
                                                            )}
                                                        >
                                                            {isUploadingReference ? (
                                                                <Loader2 className="size-4 animate-spin text-black/60" />
                                                            ) : (
                                                                <Icon
                                                                    name="plus"
                                                                    className={cn(
                                                                        'size-4',
                                                                        isAttachDisabled
                                                                            ? 'fill-black/40 dark:fill-white/40'
                                                                            : 'fill-black'
                                                                    )}
                                                                />
                                                            )}
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={
                                                                handleRegenerateImage
                                                            }
                                                            disabled={
                                                                isRegenerateSubmitDisabled
                                                            }
                                                            className={cn(
                                                                'flex h-9 w-9 items-center justify-center rounded-full border transition',
                                                                isRegenerateSubmitDisabled
                                                                    ? 'cursor-not-allowed border-grey bg-black/5 text-black/40 dark:border-white/10 dark:bg-white/10 dark:text-white/40'
                                                                    : 'border-grey bg-[#bee6f0] text-black dark:border-white/10'
                                                            )}
                                                        >
                                                            {isRegeneratingImage ? (
                                                                <Loader2 className="size-4 animate-spin text-black/60" />
                                                            ) : (
                                                                <Icon
                                                                    name="arrow-up"
                                                                    className={cn(
                                                                        'size-4',
                                                                        isRegenerateSubmitDisabled
                                                                            ? 'text-black/40 dark:text-white/40'
                                                                            : 'text-black'
                                                                    )}
                                                                />
                                                            )}
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="hidden md:flex flex-col px-0 pb-0 pt-0 overflow-hidden min-h-0">
                                        <StorybookInspectorPanel
                                            className="md:rounded-t-none md:border-t-0"
                                            selectedElement={selectedElement}
                                            onStyleChange={handleStyleChange}
                                            onTextChange={handleTextChange}
                                            pageImageUrl={
                                                currentEditPageImageUrl
                                            }
                                            textPosition={
                                                hasSeparateTextPages
                                                    ? 'separate_page'
                                                    : null
                                            }
                                        />
                                    </div>
                                </div>
                            ) : (
                                /* Normal View Mode */
                                <div className="flex flex-1 flex-col gap-4 px-3 pb-4 sm:px-5 sm:pb-5 overflow-hidden">
                                    {isMobile ? (
                                        /* Mobile Vertical Scroll View */
                                        <div
                                            ref={containerRef}
                                            className="relative flex-1 overflow-y-auto overflow-x-hidden rounded-xl scrollbar-hide"
                                        >
                                            <div className="flex flex-col gap-y-4 pb-4">
                                                {pages.map((page, index) => {
                                                    const mobilePageWidth =
                                                        containerSize.width - 24
                                                    const mobilePageHeight =
                                                        mobilePageWidth /
                                                        pageAspectRatio
                                                    return (
                                                        <div
                                                            key={page.id}
                                                            data-page-index={
                                                                index
                                                            }
                                                            className="relative flex-shrink-0 overflow-hidden rounded-xl bg-grey-3 dark:bg-[#0d1411]"
                                                            style={{
                                                                width: mobilePageWidth,
                                                                height: mobilePageHeight,
                                                                marginLeft:
                                                                    'auto',
                                                                marginRight:
                                                                    'auto'
                                                            }}
                                                        >
                                                            {useNewFormat &&
                                                            page.htmlContent ? (
                                                                <StorybookPageRenderer
                                                                    page={page}
                                                                    width={Math.floor(
                                                                        mobilePageWidth
                                                                    )}
                                                                    height={Math.floor(
                                                                        mobilePageHeight
                                                                    )}
                                                                />
                                                            ) : (
                                                                <img
                                                                    src={
                                                                        page.imageUrl ||
                                                                        ''
                                                                    }
                                                                    alt={t(
                                                                        'storybook.viewer.pageAlt',
                                                                        {
                                                                            page:
                                                                                index +
                                                                                1
                                                                        }
                                                                    )}
                                                                    className="h-full w-full object-contain"
                                                                    loading="lazy"
                                                                />
                                                            )}
                                                            {/* Page number indicator - only show on image pages */}
                                                            {page.displayPageNumber !=
                                                                null && (
                                                                <div className="absolute bottom-2 right-2 rounded-full bg-black/50 px-2 py-0.5 text-xs font-medium text-white">
                                                                    {
                                                                        page.displayPageNumber
                                                                    }
                                                                </div>
                                                            )}
                                                        </div>
                                                    )
                                                })}
                                            </div>
                                            {isGeneratingVoice && (
                                                <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/15 backdrop-blur-sm">
                                                    <Shimmer
                                                        className="text-xl font-medium"
                                                        duration={1}
                                                    >
                                                        {t(
                                                            'storybook.modal.status.generating'
                                                        )}
                                                    </Shimmer>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        /* Desktop View */
                                        <div
                                            ref={containerRef}
                                            className="relative flex-1 overflow-visible rounded-xl"
                                        >
                                            {/* Navigation Buttons */}
                                            <button
                                                onClick={prevPage}
                                                className="cursor-pointer absolute left-3 top-1/2 z-20 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-[#c6ebf7] transition hover:scale-105 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60 sm:left-1 dark:border-white/40"
                                                disabled={currentPage === 0}
                                            >
                                                <Icon
                                                    name="arrow-left-2"
                                                    className="size-6 fill-[#0f1511]"
                                                />
                                            </button>

                                            <button
                                                onClick={nextPage}
                                                className="cursor-pointer absolute right-3 top-1/2 z-20 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-[#c6ebf7] transition hover:scale-105 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60 sm:right-1 dark:border-white/40"
                                                disabled={
                                                    currentPage >=
                                                    pages.length - 1
                                                }
                                            >
                                                <Icon
                                                    name="arrow-right-2"
                                                    className="size-5 fill-[#0f1511]"
                                                />
                                            </button>

                                            {/* Book */}
                                            {containerSize.width > 0 &&
                                                containerSize.height > 0 &&
                                                pageWidth > 0 &&
                                                pageHeight > 0 && (
                                                    <div className="relative z-10 flex h-full w-full items-center justify-center">
                                                        <div
                                                            className="relative flex items-center justify-center"
                                                            style={{
                                                                width: bookWidth,
                                                                height: bookHeight
                                                            }}
                                                        >
                                                            {viewMode ===
                                                            'double' ? (
                                                                /* @ts-ignore */
                                                                <HTMLFlipBook
                                                                    key={`${viewMode}-${pageAspectRatio}-${containerSize.width}-${containerSize.height}-${currentStorybook?.id || 'legacy'}-${currentStorybook?.version || 0}-${pages.length}`}
                                                                    width={Math.floor(
                                                                        pageWidth
                                                                    )}
                                                                    height={Math.floor(
                                                                        pageHeight
                                                                    )}
                                                                    size="fixed"
                                                                    minWidth={
                                                                        260
                                                                    }
                                                                    maxWidth={
                                                                        1200
                                                                    }
                                                                    maxShadowOpacity={
                                                                        0.35
                                                                    }
                                                                    showCover={
                                                                        true
                                                                    }
                                                                    mobileScrollSupport={
                                                                        true
                                                                    }
                                                                    ref={
                                                                        bookRef
                                                                    }
                                                                    onFlip={
                                                                        handleFlip
                                                                    }
                                                                    onInit={
                                                                        handleInit
                                                                    }
                                                                    startPage={
                                                                        currentPage
                                                                    }
                                                                    usePortrait={
                                                                        false
                                                                    }
                                                                    drawShadow={
                                                                        true
                                                                    }
                                                                    flippingTime={
                                                                        800
                                                                    }
                                                                >
                                                                    {pages.map(
                                                                        (
                                                                            page,
                                                                            index
                                                                        ) => (
                                                                            <div
                                                                                key={
                                                                                    page.id
                                                                                }
                                                                                className="h-full w-full overflow-hidden bg-grey-3 dark:bg-[#0d1411]"
                                                                            >
                                                                                {useNewFormat &&
                                                                                page.htmlContent ? (
                                                                                    <StorybookPageRenderer
                                                                                        page={
                                                                                            page
                                                                                        }
                                                                                        width={Math.floor(
                                                                                            pageWidth
                                                                                        )}
                                                                                        height={Math.floor(
                                                                                            pageHeight
                                                                                        )}
                                                                                    />
                                                                                ) : (
                                                                                    <img
                                                                                        src={
                                                                                            page.imageUrl ||
                                                                                            ''
                                                                                        }
                                                                                        alt={t(
                                                                                            'storybook.viewer.pageAlt',
                                                                                            {
                                                                                                page:
                                                                                                    index +
                                                                                                    1
                                                                                            }
                                                                                        )}
                                                                                        className="h-full w-full object-contain"
                                                                                        loading="lazy"
                                                                                    />
                                                                                )}
                                                                            </div>
                                                                        )
                                                                    )}
                                                                </HTMLFlipBook>
                                                            ) : (
                                                                <div
                                                                    style={{
                                                                        width: Math.floor(
                                                                            pageWidth
                                                                        ),
                                                                        height: Math.floor(
                                                                            pageHeight
                                                                        )
                                                                    }}
                                                                    className="h-full overflow-hidden bg-grey-3 dark:bg-[#0d1411]"
                                                                >
                                                                    {useNewFormat &&
                                                                    pages[
                                                                        currentPage
                                                                    ]
                                                                        ?.htmlContent ? (
                                                                        <StorybookPageRenderer
                                                                            page={
                                                                                pages[
                                                                                    currentPage
                                                                                ]
                                                                            }
                                                                            width={Math.floor(
                                                                                pageWidth
                                                                            )}
                                                                            height={Math.floor(
                                                                                pageHeight
                                                                            )}
                                                                        />
                                                                    ) : (
                                                                        <img
                                                                            src={
                                                                                pages[
                                                                                    currentPage
                                                                                ]
                                                                                    ?.imageUrl ||
                                                                                ''
                                                                            }
                                                                            alt={t(
                                                                                'storybook.viewer.pageAlt',
                                                                                {
                                                                                    page:
                                                                                        currentPage +
                                                                                        1
                                                                                }
                                                                            )}
                                                                            className="h-full w-full object-contain"
                                                                        />
                                                                    )}
                                                                </div>
                                                            )}
                                                            {isGeneratingVoice && (
                                                                <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/15 backdrop-blur-sm">
                                                                    <Shimmer
                                                                        className="text-xl font-medium"
                                                                        duration={
                                                                            1
                                                                        }
                                                                    >
                                                                        {t(
                                                                            'storybook.modal.status.generating'
                                                                        )}
                                                                    </Shimmer>
                                                                </div>
                                                            )}
                                                        </div>

                                                        {/* Page Counter */}
                                                        <div className="pointer-events-none absolute -bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-full border border-white/10 bg-black/30 px-3 py-1 text-xs font-semibold text-white/90 backdrop-blur">
                                                            {(() => {
                                                                // Only count non-text-only pages
                                                                const total =
                                                                    pages.filter(
                                                                        (p) =>
                                                                            p.displayPageNumber !==
                                                                            null
                                                                    ).length

                                                                // Show single page format for single view mode or separate_page storybooks
                                                                if (
                                                                    viewMode ===
                                                                        'single' ||
                                                                    hasSeparateTextPages
                                                                ) {
                                                                    const currentDisplayNumber =
                                                                        pages[
                                                                            currentPage
                                                                        ]
                                                                            ?.displayPageNumber
                                                                    return t(
                                                                        'storybook.viewer.pageCount',
                                                                        {
                                                                            current:
                                                                                currentDisplayNumber ??
                                                                                currentPage +
                                                                                    1,
                                                                            total
                                                                        }
                                                                    )
                                                                }

                                                                if (
                                                                    currentPage ===
                                                                    0
                                                                ) {
                                                                    const firstDisplayNumber =
                                                                        pages[0]
                                                                            ?.displayPageNumber
                                                                    return t(
                                                                        'storybook.viewer.pageCount',
                                                                        {
                                                                            current:
                                                                                firstDisplayNumber ??
                                                                                1,
                                                                            total
                                                                        }
                                                                    )
                                                                }

                                                                const lowIndex =
                                                                    currentPage %
                                                                        2 ===
                                                                    1
                                                                        ? currentPage
                                                                        : currentPage -
                                                                          1
                                                                const highIndex =
                                                                    lowIndex + 1
                                                                const lowDisplayNumber =
                                                                    pages[
                                                                        lowIndex
                                                                    ]
                                                                        ?.displayPageNumber
                                                                const highDisplayNumber =
                                                                    pages[
                                                                        highIndex
                                                                    ]
                                                                        ?.displayPageNumber

                                                                if (
                                                                    highIndex <
                                                                    pages.length
                                                                ) {
                                                                    return t(
                                                                        'storybook.viewer.pageRange',
                                                                        {
                                                                            start:
                                                                                lowDisplayNumber ??
                                                                                lowIndex +
                                                                                    1,
                                                                            end:
                                                                                highDisplayNumber ??
                                                                                highIndex +
                                                                                    1,
                                                                            total
                                                                        }
                                                                    )
                                                                }
                                                                return t(
                                                                    'storybook.viewer.pageCount',
                                                                    {
                                                                        current:
                                                                            lowDisplayNumber ??
                                                                            lowIndex +
                                                                                1,
                                                                        total
                                                                    }
                                                                )
                                                            })()}
                                                        </div>
                                                    </div>
                                                )}
                                        </div>
                                    )}

                                    {/* Thumbnail bar - hidden on mobile for vertical scroll */}
                                    <div
                                        className={cn(
                                            'rounded-xl px-3 py-2 sm:px-4 sm:py-3 flex justify-center',
                                            isMobile && 'hidden'
                                        )}
                                    >
                                        <div
                                            ref={viewerThumbsRef}
                                            className="scrollbar-hide flex items-center gap-3 overflow-x-auto pb-1"
                                        >
                                            {pages.map((page, index) => {
                                                const isActive =
                                                    viewMode === 'single'
                                                        ? index === currentPage
                                                        : currentPage === 0
                                                          ? index === 0
                                                          : index ===
                                                                (currentPage %
                                                                    2 ===
                                                                1
                                                                    ? currentPage
                                                                    : currentPage -
                                                                      1) ||
                                                            index ===
                                                                (currentPage %
                                                                    2 ===
                                                                1
                                                                    ? currentPage
                                                                    : currentPage -
                                                                      1) +
                                                                    1

                                                // For new format with HTML, use StorybookPageThumbnail
                                                if (
                                                    useNewFormat &&
                                                    page.htmlContent
                                                ) {
                                                    return (
                                                        <div
                                                            key={page.id}
                                                            data-thumb-index={
                                                                index
                                                            }
                                                            className="flex-shrink-0"
                                                        >
                                                            <StorybookPageThumbnail
                                                                page={page}
                                                                isActive={
                                                                    isActive
                                                                }
                                                                onClick={() =>
                                                                    jumpToPage(
                                                                        index
                                                                    )
                                                                }
                                                            />
                                                        </div>
                                                    )
                                                }

                                                // Legacy image thumbnail
                                                return (
                                                    <button
                                                        key={page.id}
                                                        data-thumb-index={index}
                                                        onClick={() =>
                                                            jumpToPage(index)
                                                        }
                                                        className={cn(
                                                            'relative h-[4.5rem] w-[3.5rem] flex-shrink-0 overflow-hidden rounded-lg border transition-all duration-200 sm:h-20 sm:w-16',
                                                            isActive
                                                                ? 'border-[#bfefff]'
                                                                : 'border-black/10 opacity-60 hover:opacity-100 dark:border-white/5'
                                                        )}
                                                    >
                                                        <img
                                                            src={
                                                                page.imageUrl ||
                                                                ''
                                                            }
                                                            alt={t(
                                                                'storybook.viewer.pageAlt',
                                                                {
                                                                    page:
                                                                        index +
                                                                        1
                                                                }
                                                            )}
                                                            className="h-full w-full object-cover"
                                                        />
                                                        <span className="absolute bottom-1 right-1 rounded-full bg-black/60 px-2 text-[10px] font-semibold text-white">
                                                            {index + 1}
                                                        </span>
                                                    </button>
                                                )
                                            })}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </motion.div>
            <ShareConversation
                open={isShareOpen}
                onOpenChange={setIsShareOpen}
                sessionId={currentStorybook?.sessionId}
                storybookId={currentStorybook?.id}
            />
            <Dialog
                open={isUnsavedChangesOpen}
                onOpenChange={setIsUnsavedChangesOpen}
            >
                <DialogContent
                    showCloseButton={false}
                    overlayClassName="bg-cyan-900/20 backdrop-blur-[2px]"
                    className="light border-none bg-white dark:bg-white text-black dark:text-black shadow-2xl sm:max-w-xl min-h-[220px] flex flex-col justify-between"
                >
                    <DialogHeader>
                        <DialogTitle className="text-lg font-bold text-black dark:text-black">
                            {t('storybook.modal.unsavedChanges.title')}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="my-2 flex items-start gap-3 rounded-lg border border-orange-100 dark:border-orange-100 bg-orange-50 dark:bg-orange-50 p-4 flex-grow">
                        <TriangleAlert className="mt-0.5 flex-shrink-0 text-orange-600 size-5" />
                        <span className="text-xs text-orange-900 dark:text-orange-900">
                            <Trans
                                i18nKey="storybook.modal.unsavedChanges.warning"
                                components={{ b: <b /> }}
                            >
                                Make sure to save all your changes before
                                exiting <b>Edit mode</b>, or you risk losing
                                everything you haven&apos;t changed.
                            </Trans>
                        </span>
                    </div>
                    <DialogFooter className="mt-2 flex w-full flex-row items-center sm:justify-between">
                        {' '}
                        <Button
                            variant="outline"
                            onClick={() => setIsUnsavedChangesOpen(false)}
                            className="border-gray-200 dark:border-gray-200 text-gray-900 dark:text-gray-900 hover:bg-gray-100 dark:hover:bg-gray-100"
                        >
                            {t('storybook.modal.unsavedChanges.keepEditing')}
                        </Button>
                        <div className="flex gap-2">
                            <Button
                                onClick={async () => {
                                    const result = await performSave()
                                    if (!result.storybook) return
                                    if (!result.voiceSuccess) {
                                        setIsUnsavedChangesOpen(false)
                                        setPendingAction(null)
                                        return
                                    }
                                    setIsUnsavedChangesOpen(false)
                                    if (pendingAction === 'close-modal') {
                                        closeModal()
                                    } else {
                                        queueResumePageFromEdit()
                                        exitEditMode()
                                    }
                                    setPendingAction(null)
                                }}
                                disabled={isSavingEdits}
                                className="border-none bg-[#bee6f0] dark:bg-[#bee6f0] text-cyan-950 dark:text-cyan-950 hover:bg-[#a0def0] dark:hover:bg-[#a0def0]"
                            >
                                {isSavingEdits
                                    ? t('common.saving')
                                    : t(
                                          'storybook.modal.unsavedChanges.saveChanges'
                                      )}
                            </Button>
                            <Button
                                variant="ghost"
                                className="text-red-500 dark:text-red-500 hover:bg-red-50 dark:hover:bg-red-50 hover:text-red-600 dark:hover:text-red-600"
                                onClick={() => {
                                    discardAllChanges()
                                    setIsUnsavedChangesOpen(false)
                                    if (pendingAction === 'close-modal') {
                                        closeModal()
                                    } else {
                                        queueResumePageFromEdit()
                                        exitEditMode()
                                    }
                                    setPendingAction(null)
                                }}
                            >
                                {t(
                                    'storybook.modal.unsavedChanges.discardChanges'
                                )}
                            </Button>
                        </div>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </AnimatePresence>
    )
}

export interface StorybookModalProps {
    isShareMode?: boolean
    publicView?: boolean
}

// Main export component that wraps the inner component with providers
export function StorybookModal({
    isShareMode = false,
    publicView = false
}: StorybookModalProps): ReactElement | null {
    const { refreshAfterEdit } = useStorybook()

    const handleSaveComplete = useCallback(
        (newStorybook: Storybook) => {
            refreshAfterEdit(newStorybook)
        },
        [refreshAfterEdit]
    )

    return (
        <StorybookEditProvider onSaveComplete={handleSaveComplete}>
            <StorybookModalInner
                isShareMode={isShareMode}
                publicView={publicView}
            />
        </StorybookEditProvider>
    )
}

interface StorybookThumbnailProps {
    images: StorybookImage[]
    storybookId?: string
    isShareMode?: boolean
}

export function StorybookThumbnail({
    images,
    storybookId,
    isShareMode = false
}: StorybookThumbnailProps): ReactElement | null {
    const { t } = useTranslation()
    const { openModal, loadStorybook, loadPublicStorybook, isLoading } =
        useStorybook()

    if (!images || images.length === 0) return null

    const pageCount = images.length

    const handleClick = async (): Promise<void> => {
        if (storybookId) {
            try {
                // Use public API for shared conversations, regular API otherwise
                if (isShareMode) {
                    await loadPublicStorybook(storybookId)
                } else {
                    await loadStorybook(storybookId)
                }
            } catch {
                // Fallback to legacy mode with just images
                openModal(images)
            }
        } else {
            openModal(images)
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent): void => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            void handleClick()
        }
    }

    return (
        <div
            onClick={() => void handleClick()}
            onKeyDown={handleKeyDown}
            className={cn(
                'relative group cursor-pointer mb-4',
                isLoading && 'pointer-events-none opacity-70'
            )}
            role="button"
            tabIndex={0}
        >
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 p-2 border border-black/10 dark:border-white/10 rounded-xl bg-white dark:bg-black/20 group-hover:bg-black/5 dark:group-hover:bg-white/5 transition-colors">
                {images.map((image, index) => (
                    <div
                        key={index}
                        className="relative aspect-[3/4] overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800"
                    >
                        <img
                            src={image.url}
                            alt={t('storybook.viewer.pageAlt', {
                                page: index + 1
                            })}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        />
                        <div className="absolute top-1 right-1 px-1.5 py-0.5 bg-black/60 text-white text-[9px] font-bold rounded backdrop-blur-[2px]">
                            {index + 1}
                        </div>
                    </div>
                ))}
            </div>

            <div className="absolute bottom-4 right-4 px-3 py-1.5 bg-black/80 text-white text-xs font-semibold rounded-lg backdrop-blur-md shadow-lg border border-white/10">
                {t('storybook.thumbnail.pageCountLabel', { count: pageCount })}
            </div>

            <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all rounded-xl pointer-events-none">
                <span className="md:opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 text-white font-semibold text-sm transition-all duration-300 bg-black/80 px-4 py-2 rounded-full backdrop-blur-md border border-white/10 shadow-xl flex items-center gap-2">
                    <Icon
                        name="mode-storybook"
                        className="size-4 fill-current"
                    />
                    {t('storybook.thumbnail.readStorybook')}
                </span>
            </div>
        </div>
    )
}
