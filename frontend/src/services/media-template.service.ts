import axiosInstance from '@/lib/axios'
import type { ChatMediaType } from '@/constants/media-type-config'

export interface MediaTemplate {
    id: string
    name: string
    type: ChatMediaType
    prompt?: string
    preview?: string
}

export interface MediaTemplatesResponse {
    templates: MediaTemplate[]
    total: number
    page: number
    page_size: number
    total_pages: number
}

class MediaTemplateService {
    async getMediaTemplates(
        page: number = 0,
        pageSize: number = 20,
        type?: ChatMediaType,
        name?: string
    ): Promise<MediaTemplatesResponse> {
        const params = new URLSearchParams({
            page: page.toString(),
            page_size: pageSize.toString()
        })

        if (type) {
            params.append('type', type)
        }

        if (name) {
            params.append('name', name)
        }

        const response = await axiosInstance.get<MediaTemplatesResponse>(
            `/v1/media-templates?${params.toString()}`
        )
        return response.data
    }

    async getMediaTemplate(templateId: string): Promise<MediaTemplate> {
        const response = await axiosInstance.get<MediaTemplate>(
            `/v1/media-templates/${templateId}`
        )
        return response.data
    }
}

export const mediaTemplateService = new MediaTemplateService()
