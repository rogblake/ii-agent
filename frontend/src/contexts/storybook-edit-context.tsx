/**
 * Storybook Edit Context
 *
 * Manages multi-page edit state for storybook visual editing.
 * Tracks changes per page and coordinates saving all changes as a single version.
 */

import {
    createContext,
    useContext,
    useState,
    useCallback,
    useMemo,
    type ReactNode
} from 'react'
import {
    storybookService,
    type DesignChange,
    type PageChanges,
    type Storybook
} from '@/services/storybook.service'
import type { ElementInfo } from '@/components/design-mode/types'

interface StorybookEditState {
    isEditMode: boolean
    editingStorybookId: string | null
    currentEditPage: number | null
    pageChanges: Map<number, DesignChange[]>
    pageImageUrls: Map<number, string>
    selectedElement: ElementInfo | null
    hasUnsavedChanges: boolean
    isSaving: boolean
    saveError: string | null
}

interface StorybookEditContextValue extends StorybookEditState {
    // Mode control
    enterEditMode: (storybookId: string, initialPage?: number) => void
    exitEditMode: () => void

    // Page navigation in edit mode
    setCurrentEditPage: (pageNumber: number) => void

    // Element selection
    setSelectedElement: (element: ElementInfo | null) => void

    // Change management
    addChange: (pageNumber: number, change: DesignChange) => void
    undoLastChange: (pageNumber: number) => void
    getPageChanges: (pageNumber: number) => DesignChange[]
    getPageHasChanges: (pageNumber: number) => boolean
    getPagesWithChanges: () => number[]

    // Image URL management (for AI regenerated images)
    setPageImageUrl: (pageNumber: number, imageUrl: string) => void
    getPageImageUrl: (pageNumber: number) => string | undefined

    // Save/discard
    saveAllChanges: (selectedKeys?: Set<string>) => Promise<Storybook | null>
    discardAllChanges: () => void

    // Computed
    totalChangesCount: number
}

const StorybookEditContext = createContext<
    StorybookEditContextValue | undefined
>(undefined)

function getChangeKey(change: DesignChange): string {
    return `${change.designId}:${change.type}:${change.property}`
}

export function useStorybookEdit(): StorybookEditContextValue {
    const context = useContext(StorybookEditContext)
    if (!context) {
        throw new Error(
            'useStorybookEdit must be used within StorybookEditProvider'
        )
    }
    return context
}

interface StorybookEditProviderProps {
    children: ReactNode
    onSaveComplete?: (newStorybook: Storybook) => void
}

export function StorybookEditProvider({
    children,
    onSaveComplete
}: StorybookEditProviderProps) {
    // Edit mode state
    const [isEditMode, setIsEditMode] = useState(false)
    const [editingStorybookId, setEditingStorybookId] = useState<string | null>(
        null
    )
    const [currentEditPage, setCurrentEditPage] = useState<number | null>(null)
    const [pageChanges, setPageChanges] = useState<Map<number, DesignChange[]>>(
        new Map()
    )
    const [pageImageUrls, setPageImageUrls] = useState<Map<number, string>>(
        new Map()
    )
    const [selectedElement, setSelectedElement] = useState<ElementInfo | null>(
        null
    )
    const [isSaving, setIsSaving] = useState(false)
    const [saveError, setSaveError] = useState<string | null>(null)

    // Computed: total changes count across all pages
    const totalChangesCount = useMemo(() => {
        let count = 0
        for (const [pageNumber, changes] of pageChanges.entries()) {
            const grouped = new Set<string>()
            for (const change of changes) {
                if (change.groupId) {
                    const key = `${pageNumber}:${change.groupId}`
                    if (grouped.has(key)) continue
                    grouped.add(key)
                    count += 1
                } else {
                    count += 1
                }
            }
        }
        return count
    }, [pageChanges])

    // Computed: check if there are unsaved changes (includes image regenerations)
    const hasUnsavedChanges = totalChangesCount > 0 || pageImageUrls.size > 0

    // Enter edit mode
    const enterEditMode = useCallback(
        (storybookId: string, initialPage: number = 1) => {
            setEditingStorybookId(storybookId)
            setCurrentEditPage(initialPage)
            setPageChanges(new Map())
            setPageImageUrls(new Map())
            setSelectedElement(null)
            setSaveError(null)
            setIsEditMode(true)
        },
        []
    )

    // Exit edit mode
    const exitEditMode = useCallback(() => {
        setIsEditMode(false)
        setEditingStorybookId(null)
        setCurrentEditPage(null)
        setPageChanges(new Map())
        setPageImageUrls(new Map())
        setSelectedElement(null)
        setSaveError(null)
    }, [])

    // Add a change for a specific page with smart merge
    const addChange = useCallback(
        (pageNumber: number, change: DesignChange) => {
            setPageChanges((prev) => {
                // Skip no-op changes where from === to
                if (change.value.from === change.value.to) {
                    return prev
                }

                const newMap = new Map(prev)
                const existingChanges = newMap.get(pageNumber) || []
                const changeKey = getChangeKey(change)
                const existingIndex = existingChanges.findIndex(
                    (c) => getChangeKey(c) === changeKey
                )

                // No existing change - add new one
                if (existingIndex < 0) {
                    newMap.set(pageNumber, [...existingChanges, change])
                    return newMap
                }

                // Merge with existing: keep original 'from', update 'to'
                const existing = existingChanges[existingIndex]
                const mergedChange: DesignChange = {
                    ...change,
                    value: {
                        from: existing.value.from,
                        to: change.value.to
                    }
                }

                const newChanges = [...existingChanges]

                // If reverted to original, remove the change
                if (mergedChange.value.to === mergedChange.value.from) {
                    newChanges.splice(existingIndex, 1)
                    if (newChanges.length === 0) {
                        newMap.delete(pageNumber)
                    } else {
                        newMap.set(pageNumber, newChanges)
                    }
                } else {
                    newChanges[existingIndex] = mergedChange
                    newMap.set(pageNumber, newChanges)
                }

                return newMap
            })
        },
        []
    )

    // Undo the last change for a specific page
    const undoLastChange = useCallback((pageNumber: number) => {
        setPageChanges((prev) => {
            const changes = prev.get(pageNumber)
            if (!changes || changes.length === 0) return prev

            // Find the latest change by timestamp
            const latest = changes.reduce((acc, c) =>
                c.timestamp > acc.timestamp ? c : acc
            )

            // Filter out changes to remove (all in group if grouped, otherwise just latest)
            const shouldRemove = (c: DesignChange): boolean => {
                if (latest.groupId) {
                    return c.groupId === latest.groupId
                }
                return getChangeKey(c) === getChangeKey(latest)
            }

            const newChanges = changes.filter((c) => !shouldRemove(c))
            const newMap = new Map(prev)

            if (newChanges.length === 0) {
                newMap.delete(pageNumber)
            } else {
                newMap.set(pageNumber, newChanges)
            }

            return newMap
        })
    }, [])

    // Get changes for a specific page
    const getPageChanges = useCallback(
        (pageNumber: number): DesignChange[] => {
            return pageChanges.get(pageNumber) || []
        },
        [pageChanges]
    )

    // Check if a page has changes
    const getPageHasChanges = useCallback(
        (pageNumber: number): boolean => {
            const changes = pageChanges.get(pageNumber)
            return changes !== undefined && changes.length > 0
        },
        [pageChanges]
    )

    // Get list of pages with changes
    const getPagesWithChanges = useCallback((): number[] => {
        return Array.from(pageChanges.entries())
            .filter(([, changes]) => changes.length > 0)
            .map(([pageNumber]) => pageNumber)
            .sort((a, b) => a - b)
    }, [pageChanges])

    // Set regenerated image URL for a page
    const setPageImageUrl = useCallback(
        (pageNumber: number, imageUrl: string) => {
            setPageImageUrls((prev) => {
                const newMap = new Map(prev)
                newMap.set(pageNumber, imageUrl)
                return newMap
            })
        },
        []
    )

    // Get regenerated image URL for a page
    const getPageImageUrl = useCallback(
        (pageNumber: number): string | undefined => {
            return pageImageUrls.get(pageNumber)
        },
        [pageImageUrls]
    )

    // Helper to check if a change matches a selected key
    const isChangeSelected = useCallback(
        (
            pageNumber: number,
            change: DesignChange,
            selectedKeys: Set<string>
        ): boolean => {
            if (change.groupId) {
                const key = `${pageNumber}-${change.groupId}`
                return selectedKeys.has(key)
            }
            const key = `${pageNumber}-${change.designId}-${change.property}-${change.timestamp}`
            return selectedKeys.has(key)
        },
        []
    )

    // Save all changes (or only selected changes if selectedKeys is provided)
    const saveAllChanges = useCallback(
        async (selectedKeys?: Set<string>): Promise<Storybook | null> => {
            if (!editingStorybookId || !hasUnsavedChanges) {
                return null
            }

            setIsSaving(true)
            setSaveError(null)

            try {
                // Convert Map to array of PageChanges, filtering by selectedKeys if provided
                // Only filter if selectedKeys has items; empty Set means save all
                const shouldFilter = selectedKeys && selectedKeys.size > 0

                // Collect all pages that have changes or regenerated images
                const allPageNumbers = new Set<number>([
                    ...pageChanges.keys(),
                    ...pageImageUrls.keys()
                ])

                const pageChangesArray: PageChanges[] = Array.from(
                    allPageNumbers
                )
                    .map((page_number) => {
                        const changes = pageChanges.get(page_number) || []
                        const filteredChanges = shouldFilter
                            ? changes.filter((change) =>
                                  isChangeSelected(
                                      page_number,
                                      change,
                                      selectedKeys
                                  )
                              )
                            : changes
                        const image_url = pageImageUrls.get(page_number)
                        return { page_number, changes: filteredChanges, image_url }
                    })
                    .filter(
                        ({ changes, image_url }) =>
                            changes.length > 0 || image_url !== undefined
                    )

                if (pageChangesArray.length === 0) {
                    return null
                }

                const response = await storybookService.saveAllEdits(
                    editingStorybookId,
                    pageChangesArray
                )

                if (!response.success) {
                    setSaveError(response.error || 'Failed to save changes')
                    return null
                }

                // Remove saved changes from state
                if (shouldFilter) {
                    // Only remove the changes that were saved
                    setPageChanges((prev) => {
                        const newMap = new Map<number, DesignChange[]>()
                        for (const [pageNumber, changes] of prev.entries()) {
                            const remainingChanges = changes.filter(
                                (change) =>
                                    !isChangeSelected(
                                        pageNumber,
                                        change,
                                        selectedKeys!
                                    )
                            )
                            if (remainingChanges.length > 0) {
                                newMap.set(pageNumber, remainingChanges)
                            }
                        }
                        return newMap
                    })
                    // Note: pageImageUrls are always cleared on save (not selectable)
                } else {
                    // Clear all changes
                    setPageChanges(new Map())
                }

                // Clear regenerated image URLs (always saved together)
                setPageImageUrls(new Map())

                // Update editing storybook ID to the new version
                if (response.storybook) {
                    setEditingStorybookId(response.storybook.id)
                }

                // Notify parent of new storybook
                if (response.storybook && onSaveComplete) {
                    onSaveComplete(response.storybook)
                }

                return response.storybook
            } catch (error) {
                const message =
                    error instanceof Error
                        ? error.message
                        : 'Unknown error saving changes'
                setSaveError(message)
                return null
            } finally {
                setIsSaving(false)
            }
        },
        [
            editingStorybookId,
            hasUnsavedChanges,
            pageChanges,
            pageImageUrls,
            onSaveComplete,
            isChangeSelected
        ]
    )

    // Discard all changes
    const discardAllChanges = useCallback(() => {
        setPageChanges(new Map())
        setPageImageUrls(new Map())
        setSaveError(null)
    }, [])

    const value: StorybookEditContextValue = useMemo(
        () => ({
            // State
            isEditMode,
            editingStorybookId,
            currentEditPage,
            pageChanges,
            pageImageUrls,
            selectedElement,
            hasUnsavedChanges,
            isSaving,
            saveError,

            // Actions
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
            getPageImageUrl,
            saveAllChanges,
            discardAllChanges,

            // Computed
            totalChangesCount
        }),
        [
            isEditMode,
            editingStorybookId,
            currentEditPage,
            pageChanges,
            pageImageUrls,
            selectedElement,
            hasUnsavedChanges,
            isSaving,
            saveError,
            enterEditMode,
            exitEditMode,
            addChange,
            undoLastChange,
            getPageChanges,
            getPageHasChanges,
            getPagesWithChanges,
            setPageImageUrl,
            getPageImageUrl,
            saveAllChanges,
            discardAllChanges,
            totalChangesCount
        ]
    )

    return (
        <StorybookEditContext.Provider value={value}>
            {children}
        </StorybookEditContext.Provider>
    )
}

export type { DesignChange, StorybookEditState }
