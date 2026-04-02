import {
    createContext,
    useCallback,
    useContext,
    useState,
    useMemo
} from 'react'
import type { ReactElement, ReactNode } from 'react'
import {
    storybookService,
    type Storybook,
    type StorybookPage
} from '@/services/storybook.service'

// Legacy interface for backward compatibility
export interface StorybookImage {
    url: string
}

// New interface for storybook page data
export interface StorybookPageData {
    id: string
    pageNumber: number
    displayPageNumber: number | null // Sequential number counting only image pages (null for text-only pages)
    imageUrl: string | null
    htmlContent: string | null
    textContent?: string | null
    audioLink?: string | null
    metadata: Record<string, unknown> | null
}

// Full storybook data interface
export interface StorybookData {
    id: string
    name: string
    version: number
    sessionId: string
    parentStorybookId: string | null
    styleJson: Record<string, unknown> | null
    aspectRatio: string
    resolution: string
    pages: StorybookPageData[]
}

// Edit mode state
export interface EditState {
    isEditing: boolean
    pageNumber: number | null
    editType: 'text' | 'image' | null
}

interface StorybookContextValue {
    // Modal state
    isModalOpen: boolean
    openModal: (data: StorybookImage[] | StorybookData) => void
    closeModal: () => void

    // Legacy support
    images: StorybookImage[]

    // New storybook data
    currentStorybook: StorybookData | null
    isLoading: boolean
    error: string | null

    // Load storybook from API
    loadStorybook: (storybookId: string) => Promise<void>
    loadPublicStorybook: (storybookId: string) => Promise<void>

    // Edit operations
    editState: EditState
    startEditingText: (pageNumber: number) => void
    startEditingImage: (pageNumber: number) => void
    cancelEditing: () => void

    // Helpers
    getCurrentPage: () => StorybookPageData | null
    getPage: (pageNumber: number) => StorybookPageData | null

    // Version switching
    switchToVersion: (storybookId: string) => Promise<void>
    refreshAfterEdit: (newStorybook: Storybook) => void
}

const StorybookContext = createContext<StorybookContextValue | undefined>(
    undefined
)

const EXIT_ANIMATION_DELAY_MS = 300

export function useStorybook(): StorybookContextValue {
    const context = useContext(StorybookContext)
    if (!context) {
        throw new Error('useStorybook must be used within StorybookProvider')
    }
    return context
}

// Helper to convert API response to StorybookData
function apiStorybookToData(storybook: Storybook): StorybookData {
    // Calculate display page numbers (sequential, counting only image pages)
    let displayNum = 1
    const pages = (storybook.pages || []).map((page) => {
        const isTextOnlyPage = page.metadata?.is_text_only_page === true
        const displayPageNumber = isTextOnlyPage ? null : displayNum++
        return apiPageToData(page, displayPageNumber)
    })

    return {
        id: storybook.id,
        name: storybook.name,
        version: storybook.version,
        sessionId: storybook.session_id,
        parentStorybookId: storybook.parent_storybook_id,
        styleJson: storybook.style_json ?? null,
        aspectRatio: storybook.aspect_ratio,
        resolution: storybook.resolution,
        pages
    }
}

function apiPageToData(
    page: StorybookPage,
    displayPageNumber: number | null
): StorybookPageData {
    return {
        id: page.id,
        pageNumber: page.page_number,
        displayPageNumber,
        imageUrl: page.image_url,
        htmlContent: page.html_content,
        textContent: page.text_content ?? null,
        audioLink: page.audio_link ?? null,
        metadata: page.metadata
    }
}

interface StorybookProviderProps {
    children: ReactNode
}

export function StorybookProvider({
    children
}: StorybookProviderProps): ReactElement {
    // Modal state
    const [isModalOpen, setIsModalOpen] = useState(false)

    // Legacy images support
    const [images, setImages] = useState<StorybookImage[]>([])

    // New storybook data
    const [currentStorybook, setCurrentStorybook] =
        useState<StorybookData | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    // Current page index for viewing
    const [currentPageIndex, setCurrentPageIndex] = useState(0)

    // Edit state
    const [editState, setEditState] = useState<EditState>({
        isEditing: false,
        pageNumber: null,
        editType: null
    })

    // Open modal with either legacy images or new storybook data
    const openModal = useCallback((data: StorybookImage[] | StorybookData) => {
        if (Array.isArray(data)) {
            // Legacy format: array of images
            setImages(data)
            setCurrentStorybook(null)
        } else {
            // New format: full storybook data
            setCurrentStorybook(data)
            // Also set images for backward compatibility
            setImages(
                data.pages
                    .filter((p) => p.imageUrl)
                    .map((p) => ({ url: p.imageUrl! }))
            )
        }
        setCurrentPageIndex(0)
        setEditState({ isEditing: false, pageNumber: null, editType: null })
        setIsModalOpen(true)
    }, [])

    // Close modal
    const closeModal = useCallback(() => {
        setIsModalOpen(false)
        setEditState({ isEditing: false, pageNumber: null, editType: null })
        setTimeout(() => {
            setImages([])
            setCurrentStorybook(null)
            setCurrentPageIndex(0)
        }, EXIT_ANIMATION_DELAY_MS)
    }, [])

    // Load storybook from API
    const loadStorybook = useCallback(async (storybookId: string) => {
        setIsLoading(true)
        setError(null)
        try {
            let targetStorybookId = storybookId
            try {
                const versionHistory =
                    await storybookService.getVersionHistory(storybookId)
                if (versionHistory.versions.length > 0) {
                    const latestVersion = versionHistory.versions.reduce(
                        (latest, version) =>
                            version.version > latest.version ? version : latest,
                        versionHistory.versions[0]
                    )
                    targetStorybookId = latestVersion.id
                }
            } catch (err) {
                console.warn(
                    '[StorybookContext] Failed to load version history:',
                    err
                )
            }

            const storybook =
                await storybookService.getStorybook(targetStorybookId)
            const data = apiStorybookToData(storybook)
            setCurrentStorybook(data)
            setImages(
                data.pages
                    .filter((p) => p.imageUrl)
                    .map((p) => ({ url: p.imageUrl! }))
            )
            setCurrentPageIndex(0)
            setIsModalOpen(true)
        } catch (err) {
            setError(
                err instanceof Error ? err.message : 'Failed to load storybook'
            )
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [])

    // Load public storybook
    const loadPublicStorybook = useCallback(async (storybookId: string) => {
        setIsLoading(true)
        setError(null)
        try {
            const storybook =
                await storybookService.getPublicStorybook(storybookId)
            const data = apiStorybookToData(storybook)
            setCurrentStorybook(data)
            setImages(
                data.pages
                    .filter((p) => p.imageUrl)
                    .map((p) => ({ url: p.imageUrl! }))
            )
            setIsModalOpen(true)
        } catch (err) {
            setError(
                err instanceof Error ? err.message : 'Failed to load storybook'
            )
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [])

    // Start editing text
    const startEditingText = useCallback((pageNumber: number) => {
        setEditState({
            isEditing: true,
            pageNumber,
            editType: 'text'
        })
    }, [])

    // Start editing image
    const startEditingImage = useCallback((pageNumber: number) => {
        setEditState({
            isEditing: true,
            pageNumber,
            editType: 'image'
        })
    }, [])

    // Cancel editing
    const cancelEditing = useCallback(() => {
        setEditState({
            isEditing: false,
            pageNumber: null,
            editType: null
        })
    }, [])

    // Get current page
    const getCurrentPage = useCallback((): StorybookPageData | null => {
        if (!currentStorybook || currentStorybook.pages.length === 0) {
            return null
        }
        return currentStorybook.pages[currentPageIndex] || null
    }, [currentStorybook, currentPageIndex])

    // Get page by number
    const getPage = useCallback(
        (pageNumber: number): StorybookPageData | null => {
            if (!currentStorybook) return null
            return (
                currentStorybook.pages.find(
                    (p) => p.pageNumber === pageNumber
                ) || null
            )
        },
        [currentStorybook]
    )

    // Switch to a different version of the storybook
    const switchToVersion = useCallback(async (storybookId: string) => {
        setIsLoading(true)
        setError(null)
        try {
            const storybook = await storybookService.getStorybook(storybookId)
            const data = apiStorybookToData(storybook)
            setCurrentStorybook(data)
            setImages(
                data.pages
                    .filter((p) => p.imageUrl)
                    .map((p) => ({ url: p.imageUrl! }))
            )
            // Reset page index to beginning when switching versions
            setCurrentPageIndex(0)
        } catch (err) {
            setError(
                err instanceof Error ? err.message : 'Failed to switch version'
            )
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [])

    // Refresh the storybook after an edit (e.g., from visual edit mode)
    const refreshAfterEdit = useCallback((newStorybook: Storybook) => {
        const data = apiStorybookToData(newStorybook)
        setCurrentStorybook(data)
        setImages(
            data.pages
                .filter((p) => p.imageUrl)
                .map((p) => ({ url: p.imageUrl! }))
        )
    }, [])

    const value: StorybookContextValue = useMemo(
        () => ({
            isModalOpen,
            openModal,
            closeModal,
            images,
            currentStorybook,
            isLoading,
            error,
            loadStorybook,
            loadPublicStorybook,
            editState,
            startEditingText,
            startEditingImage,
            cancelEditing,
            getCurrentPage,
            getPage,
            switchToVersion,
            refreshAfterEdit
        }),
        [
            isModalOpen,
            openModal,
            closeModal,
            images,
            currentStorybook,
            isLoading,
            error,
            loadStorybook,
            loadPublicStorybook,
            editState,
            startEditingText,
            startEditingImage,
            cancelEditing,
            getCurrentPage,
            getPage,
            switchToVersion,
            refreshAfterEdit
        ]
    )

    return (
        <StorybookContext.Provider value={value}>
            {children}
        </StorybookContext.Provider>
    )
}
