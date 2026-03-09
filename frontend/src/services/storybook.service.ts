import axiosInstance from '@/lib/axios'
import { ACCESS_TOKEN } from '@/constants/auth'

export interface StorybookPage {
    id: string
    storybook_id: string
    page_number: number
    image_url: string | null
    html_content: string | null
    text_content?: string | null
    audio_link?: string | null
    metadata: Record<string, unknown> | null
    created_at: string | null
    updated_at: string | null
}

export interface Storybook {
    id: string
    session_id: string
    name: string
    version: number
    parent_storybook_id: string | null
    style_json: Record<string, unknown> | null
    aspect_ratio: string
    resolution: string
    page_count: number
    created_at: string | null
    updated_at: string | null
    pages?: StorybookPage[]
}

export interface StorybookListResponse {
    session_id: string
    storybooks: Storybook[]
    total: number
}

export interface StorybookVersionResponse {
    success: boolean
    storybook: Storybook | null
    error: string | null
}

export interface StorybookVoiceOverResponse {
    success: boolean
    storybook: Storybook | null
    error: string | null
}

export interface StorybookDownloadProgress {
    type: 'progress' | 'complete' | 'error'
    current?: number
    total?: number
    message?: string
    percent?: number
    pdf_base64?: string
    zip_base64?: string
    filename?: string
    total_pages?: number
}

export interface StorybookProgressPage {
    page_number: number
    image_url: string | null
}

export interface StorybookProgressResponse {
    type: 'storybook_progress'
    storybook_id: string
    storybook_name: string
    total_pages: number
    completed_pages: number
    current_page: number
    status: 'generating' | 'completed' | 'failed'
    pages: StorybookProgressPage[]
    page?: StorybookProgressPage | null
    error_message?: string | null
    generating_pages?: number[]
}

export interface StorybookResultPage {
    page_number: number
    image_url: string
    text_content?: string | null
    audio_link?: string | null
    text_position?: string
    text_percentage?: number
}

export interface StorybookResultResponse {
    type: 'storybook'
    storybook_id: string
    storybook_name: string
    version: number
    pages: StorybookResultPage[]
    aspect_ratio: string
    resolution: string
}

export type StorybookGenerationResponse =
    | StorybookProgressResponse
    | StorybookResultResponse

export interface StorybookCancelResponse {
    success: boolean
    message?: string | null
}

// Edit mode interfaces
export interface DesignChange {
    designId: string
    type: 'style' | 'text' | 'attribute' | 'move' | 'delete'
    property: string
    value: {
        from: string | null
        to: string | null
    }
    timestamp: number
    elementContext?: Record<string, unknown>
    groupId?: string
    groupLabel?: string
}

export interface PageChanges {
    page_number: number
    changes: DesignChange[]
    image_url?: string
}

export interface SaveEditsRequest {
    storybook_id: string
    page_changes: PageChanges[]
}

export interface SaveEditsResponse {
    success: boolean
    storybook: Storybook | null
    error: string | null
}

export interface VersionInfo {
    id: string
    version: number
    created_at: string | null
    is_current: boolean
}

export interface VersionHistoryResponse {
    versions: VersionInfo[]
}

export interface StorybookBackgroundUploadResponse {
    url: string
    storage_path: string
}

export interface AIRewriteRequest {
    storybook_id: string
    content: string
    page_image_url?: string
    element_context?: Record<string, unknown>
}

export interface AIRewriteResponse {
    success: boolean
    rewritten_content?: string
    error?: string
}

export interface AIGenerateBackgroundRequest {
    storybook_id: string
    prompt: string
    page_image_url?: string
    text_position?: string
}

export interface AIGenerateBackgroundResponse {
    success: boolean
    image_url?: string
    error?: string
}

export interface AIRegenerateImageRequest {
    storybook_id: string
    page_number: number
    prompt: string
    reference_image_url?: string
    scene_text?: string
    text_position?: string
    text_percentage?: number
}

export interface AIRegenerateImageResponse {
    success: boolean
    image_url?: string
    error?: string
}

class StorybookService {
    private baseURL: string

    constructor() {
        this.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    }

    /**
     * Get all storybooks for a session
     */
    async getSessionStorybooks(
        sessionId: string,
        includePages: boolean = false
    ): Promise<StorybookListResponse> {
        const params = new URLSearchParams({
            include_pages: includePages.toString()
        })

        const response = await axiosInstance.get<StorybookListResponse>(
            `/storybooks/session/${sessionId}?${params.toString()}`
        )
        return response.data
    }

    /**
     * Get a storybook by ID with all pages
     */
    async getStorybook(storybookId: string): Promise<Storybook> {
        const response = await axiosInstance.get<Storybook>(
            `/storybooks/${storybookId}`
        )
        return response.data
    }

    /**
     * Generate voice-over audio for a storybook.
     */
    async generateStorybookVoiceOver(
        storybookId: string,
        language?: string,
        options?: { force?: boolean }
    ): Promise<StorybookVoiceOverResponse> {
        const params = new URLSearchParams()
        if (language) {
            params.set('language', language)
        }
        if (options?.force) {
            params.set('force', 'true')
        }
        const suffix = params.toString()
        const response = await axiosInstance.post<StorybookVoiceOverResponse>(
            `/storybooks/${storybookId}/voice${suffix ? `?${suffix}` : ''}`
        )
        return response.data
    }

    /**
     * Get a public storybook (no auth required)
     */
    async getPublicStorybook(storybookId: string): Promise<Storybook> {
        const response = await axiosInstance.get<Storybook>(
            `/storybooks/public/${storybookId}`
        )
        return response.data
    }

    /**
     * Get storybook generation progress (polling)
     */
    async getStorybookGenerationStatus(
        storybookId: string
    ): Promise<StorybookGenerationResponse> {
        const response = await axiosInstance.get<StorybookGenerationResponse>(
            `/storybooks/${storybookId}/progress`
        )
        return response.data
    }

    /**
     * Cancel storybook generation
     */
    async cancelStorybookGeneration(
        storybookId: string
    ): Promise<StorybookCancelResponse> {
        const response = await axiosInstance.post<StorybookCancelResponse>(
            `/storybooks/${storybookId}/cancel`
        )
        return response.data
    }

    /**
     * Download storybook as PDF (simple, no progress)
     */
    async downloadStorybookPdf(storybookId: string): Promise<Blob> {
        const response = await axiosInstance.get(
            `/storybooks/${storybookId}/download`,
            { responseType: 'blob' }
        )
        return response.data
    }

    /**
     * Download storybook as PDF with real-time progress updates
     */
    async downloadStorybookWithProgress(
        storybookId: string
    ): Promise<AsyncGenerator<StorybookDownloadProgress, void, unknown>> {
        const endpoint = `/storybooks/${storybookId}/download/stream`
        const token = localStorage.getItem(ACCESS_TOKEN)

        // Use fetch with Authorization header for streaming
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/event-stream',
            },
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return this.parseSSEStream(response)
    }

    /**
     * Parse Server-Sent Events stream and yield progress updates
     */
    private async *parseSSEStream(
        response: Response
    ): AsyncGenerator<StorybookDownloadProgress, void, unknown> {
        const reader = response.body?.getReader()
        if (!reader) {
            throw new Error('No response body')
        }

        const decoder = new TextDecoder()
        let buffer = ''

        try {
            while (true) {
                const { done, value } = await reader.read()

                if (done) break

                buffer += decoder.decode(value, { stream: true })

                // Process complete SSE messages
                const lines = buffer.split('\n\n')
                buffer = lines.pop() || ''

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data: StorybookDownloadProgress = JSON.parse(line.slice(6))
                        yield data

                        if (data.type === 'complete' || data.type === 'error') {
                            return
                        }
                    }
                }
            }
        } finally {
            reader.releaseLock()
        }
    }

    /**
     * Download a single storybook page as PDF
     */
    async downloadStorybookPagePdf(storybookId: string, pageNumber: number): Promise<Blob> {
        const response = await axiosInstance.get(
            `/storybooks/${storybookId}/download/page/${pageNumber}`,
            { responseType: 'blob' }
        )
        return response.data
    }

    /**
     * Download a single storybook page as PNG
     */
    async downloadStorybookPagePng(storybookId: string, pageNumber: number): Promise<Blob> {
        const response = await axiosInstance.get(
            `/storybooks/${storybookId}/download/png/${pageNumber}`,
            { responseType: 'blob' }
        )
        return response.data
    }

    /**
     * Download all storybook pages as a ZIP of PNGs (simple, no progress)
     */
    async downloadStorybookPngZip(storybookId: string): Promise<Blob> {
        const response = await axiosInstance.get(
            `/storybooks/${storybookId}/download/png`,
            { responseType: 'blob' }
        )
        return response.data
    }

    /**
     * Download storybook as PNG ZIP with real-time progress updates
     */
    async downloadStorybookPngWithProgress(
        storybookId: string
    ): Promise<AsyncGenerator<StorybookDownloadProgress, void, unknown>> {
        const endpoint = `/storybooks/${storybookId}/download/png/stream`
        const token = localStorage.getItem(ACCESS_TOKEN)

        // Use fetch with Authorization header for streaming
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/event-stream',
            },
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return this.parseSSEStream(response)
    }

    /**
     * Create a download link and trigger PDF file download
     */
    downloadPDFFile(base64Data: string, filename: string): void {
        this.downloadBase64File(base64Data, filename, 'application/pdf')
    }

    /**
     * Create a download link and trigger ZIP file download
     */
    downloadZIPFile(base64Data: string, filename: string): void {
        this.downloadBase64File(base64Data, filename, 'application/zip')
    }

    /**
     * Create a download link and trigger file download from base64 data
     */
    private downloadBase64File(base64Data: string, filename: string, mimeType: string): void {
        const binaryString = atob(base64Data)
        const bytes = new Uint8Array(binaryString.length)
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i)
        }
        const blob = new Blob([bytes], { type: mimeType })

        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', filename)
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.URL.revokeObjectURL(url)
    }

    // ========================
    // Edit Mode API Methods
    // ========================

    /**
     * Get the edit proxy URL for a storybook page
     * Returns the URL that can be used in an iframe to load the page with design-mode runtime
     */
    getEditProxyUrl(storybookId: string, pageNumber: number): string {
        const params = new URLSearchParams({
            page_number: pageNumber.toString()
        })
        // Return full URL for iframe src (auth handled by axios interceptor when loading via srcDoc)
        return `${this.baseURL}/storybooks/${storybookId}/edit/proxy?${params.toString()}`
    }

    /**
     * Save all page edits and create a new storybook version
     */
    async saveAllEdits(
        storybookId: string,
        pageChanges: PageChanges[]
    ): Promise<SaveEditsResponse> {
        const request: SaveEditsRequest = {
            storybook_id: storybookId,
            page_changes: pageChanges
        }
        const response = await axiosInstance.post<SaveEditsResponse>(
            `/storybooks/${storybookId}/edit/save`,
            request
        )
        return response.data
    }

    /**
     * Get version history for a storybook
     */
    async getVersionHistory(storybookId: string): Promise<VersionHistoryResponse> {
        const response = await axiosInstance.get<VersionHistoryResponse>(
            `/storybooks/${storybookId}/versions`
        )
        return response.data
    }

    /**
     * Upload a background image for storybook editing to public storage.
     */
    async uploadBackgroundImage(
        storybookId: string,
        file: File
    ): Promise<StorybookBackgroundUploadResponse> {
        const formData = new FormData()
        formData.append('file', file)

        const response = await axiosInstance.post<StorybookBackgroundUploadResponse>(
            `/storybooks/${storybookId}/edit/upload-background`,
            formData,
            {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            }
        )
        return response.data
    }

    /**
     * Use AI to rewrite text content for a storybook element.
     */
    async aiRewriteContent(
        storybookId: string,
        content: string,
        pageImageUrl?: string,
        elementContext?: Record<string, unknown>
    ): Promise<AIRewriteResponse> {
        const request: AIRewriteRequest = {
            storybook_id: storybookId,
            content,
            page_image_url: pageImageUrl,
            element_context: elementContext
        }
        const response = await axiosInstance.post<AIRewriteResponse>(
            `/storybooks/${storybookId}/edit/ai-rewrite`,
            request
        )
        return response.data
    }

    /**
     * Use AI to generate/extend a background image from a text prompt.
     */
    async aiGenerateBackground(
        storybookId: string,
        prompt: string,
        pageImageUrl?: string,
        textPosition?: string
    ): Promise<AIGenerateBackgroundResponse> {
        const request: AIGenerateBackgroundRequest = {
            storybook_id: storybookId,
            prompt,
            page_image_url: pageImageUrl,
            text_position: textPosition
        }
        const response = await axiosInstance.post<AIGenerateBackgroundResponse>(
            `/storybooks/${storybookId}/edit/ai-generate-background`,
            request
        )
        return response.data
    }

    /**
     * Use AI to regenerate a storybook image from a prompt.
     */
    async aiRegenerateImage(
        storybookId: string,
        pageNumber: number,
        prompt: string,
        referenceImageUrl?: string,
        sceneText?: string,
        textPosition?: string,
        textPercentage?: number
    ): Promise<AIRegenerateImageResponse>
    async aiRegenerateImage({
        storybookId,
        pageNumber,
        prompt,
        referenceImageUrl,
        sceneText,
        textPosition,
        textPercentage
    }: {
        storybookId: string
        pageNumber: number
        prompt: string
        referenceImageUrl?: string
        sceneText?: string
        textPosition?: string
        textPercentage?: number
    }): Promise<AIRegenerateImageResponse>
    async aiRegenerateImage(
        storybookIdOrParams:
            | string
            | {
                  storybookId: string
                  pageNumber: number
                  prompt: string
                  referenceImageUrl?: string
                  sceneText?: string
                  textPosition?: string
                  textPercentage?: number
              },
        pageNumber?: number,
        prompt?: string,
        referenceImageUrl?: string,
        sceneText?: string,
        textPosition?: string,
        textPercentage?: number
    ): Promise<AIRegenerateImageResponse> {
        const params =
            typeof storybookIdOrParams === 'string'
                ? {
                      storybookId: storybookIdOrParams,
                      pageNumber: pageNumber ?? 1,
                      prompt: prompt ?? '',
                      referenceImageUrl,
                      sceneText,
                      textPosition,
                      textPercentage
                  }
                : storybookIdOrParams

        const request: AIRegenerateImageRequest = {
            storybook_id: params.storybookId,
            page_number: params.pageNumber,
            prompt: params.prompt,
            reference_image_url: params.referenceImageUrl,
            scene_text: params.sceneText,
            text_position: params.textPosition,
            text_percentage: params.textPercentage
        }
        const response = await axiosInstance.post<AIRegenerateImageResponse>(
            `/storybooks/${params.storybookId}/edit/ai-regenerate-image`,
            request
        )
        return response.data
    }
}

export const storybookService = new StorybookService()
