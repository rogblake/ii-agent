/**
 * Storybook progress utilities
 *
 * Shared logic for parsing storybook progress data and building UI state.
 */

export interface PageSlot {
    pageNumber: number
    imageUrl: string | null
    isCompleted: boolean
    isGenerating: boolean
}

export interface StorybookProgressData {
    storybookId: string
    totalPages: number
    completedPages: number
    progressPercent: number
    progressStatus: string
    errorMessage?: string
    pageSlots: PageSlot[]
}

interface StorybookProgressContent {
    type?: string
    storybook_id?: string
    total_pages?: number
    completed_pages?: number
    status?: string
    error_message?: string
    pages?: Array<{ page_number: number; image_url: string }>
    page?: { page_number: number; image_url: string }
    generating_pages?: number[]
}

/**
 * Parse storybook progress content and build page slots array.
 */
export function parseStorybookProgress(content: StorybookProgressContent | null | undefined): StorybookProgressData | null {
    if (!content || content.type !== 'storybook_progress') {
        return null
    }

    const {
        total_pages = 0,
        completed_pages = 0,
        status = 'generating',
        error_message,
        pages = [],
        page: latestPage,
        generating_pages = [],
        storybook_id = ''
    } = content

    // Build array of all page slots
    const pageSlots: PageSlot[] = Array.from({ length: total_pages }, (_, i) => {
        const pageNum = i + 1
        const completedPageData = pages.find(p => p.page_number === pageNum)
        const isLatestCompleted = latestPage?.page_number === pageNum
        const imageUrl = completedPageData?.image_url || (isLatestCompleted ? latestPage?.image_url : null) || null
        const isGenerating = generating_pages.includes(pageNum) && status === 'generating' && !imageUrl

        return {
            pageNumber: pageNum,
            imageUrl,
            isCompleted: !!imageUrl,
            isGenerating
        }
    })

    return {
        storybookId: storybook_id || '',
        totalPages: total_pages,
        completedPages: completed_pages,
        progressPercent: total_pages > 0 ? (completed_pages / total_pages) * 100 : 0,
        progressStatus: status,
        errorMessage: error_message,
        pageSlots
    }
}

export type TranslationFn = (key: string, options?: Record<string, any>) => string

/**
 * Generate progress message based on current state.
 */
export function getStorybookProgressMessage(
    t: TranslationFn,
    totalPages: number,
    progressStatus: string,
    generatingPages: number[]
): string {
    if (progressStatus === 'failed') {
        return t('tools.storybookCancelled')
    }

    if (progressStatus !== 'generating') {
        return t('tools.storybookComplete', {
            total: totalPages
        })
    }

    const pageCount = generatingPages.length

    if (pageCount > 1) {
        return t('tools.generatingStorybookBatch', {
            pages: generatingPages.join(', '),
            total: totalPages
        })
    }

    if (pageCount === 1) {
        return t('tools.generatingStorybookProgress', {
            current: generatingPages[0],
            total: totalPages
        })
    }

    return t('tools.generatingStorybook')
}
