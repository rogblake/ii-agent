import axiosInstance from '@/lib/axios'
import type { ChatMediaModel } from '@/constants/media-models'
import type { ChatMediaType } from '@/constants/media-type-config'

export type ReferenceImageType = 'subject' | 'scene' | 'style'

export interface GenerateReferenceImageRequest {
    prompt: string
    type: ReferenceImageType
    session_id?: string
    aspect_ratio?: '1:1' | '16:9' | '9:16' | '4:3' | '3:4'
    model_name?: string
    provider?: string
}

export interface GenerateReferenceImageResponse {
    success: boolean
    url: string | null
    file_id: string | null
    error: string | null
}

export interface VideoModelsResponse {
    models: ChatMediaModel[]
    suggestions: string[]
}

export interface ImageModelsResponse {
    models: ChatMediaModel[]
    storybook_models: ChatMediaModel[]
    suggestions: string[]
    storybook_suggestions: string[]
}

export interface MediaModelsResponse {
    imageModels: ChatMediaModel[]
    storybookModels: ChatMediaModel[]
    videoModels: ChatMediaModel[]
    suggestions: Record<ChatMediaType, string[]>
}

class MediaService {
    async generateReferenceImage(
        data: GenerateReferenceImageRequest
    ): Promise<GenerateReferenceImageResponse> {
        const response = await axiosInstance.post<GenerateReferenceImageResponse>(
            '/media/reference-image',
            data
        )
        return response.data
    }

    async getVideoModels(): Promise<VideoModelsResponse> {
        const response =
            await axiosInstance.get<VideoModelsResponse>('/media/models/video')
        return response.data
    }

    async getImageModels(): Promise<ImageModelsResponse> {
        const response =
            await axiosInstance.get<ImageModelsResponse>('/media/models/image')
        return response.data
    }

    async getAllMediaModels(): Promise<MediaModelsResponse> {
        const [videoResult, imageResult] = await Promise.allSettled([
            this.getVideoModels(),
            this.getImageModels()
        ])

        // Extract successful responses, use empty defaults for failures
        const videoResponse: VideoModelsResponse =
            videoResult.status === 'fulfilled'
                ? videoResult.value
                : { models: [], suggestions: [] }

        const imageResponse: ImageModelsResponse =
            imageResult.status === 'fulfilled'
                ? imageResult.value
                : { models: [], storybook_models: [], suggestions: [], storybook_suggestions: [] }

        // Log failures for debugging but don't throw
        if (videoResult.status === 'rejected') {
            console.warn('Failed to fetch video models:', videoResult.reason)
        }
        if (imageResult.status === 'rejected') {
            console.warn('Failed to fetch image models:', imageResult.reason)
        }

        return {
            imageModels: imageResponse.models,
            storybookModels: imageResponse.storybook_models,
            videoModels: videoResponse.models,
            suggestions: {
                image: imageResponse.suggestions,
                storybook: imageResponse.storybook_suggestions,
                video: videoResponse.suggestions,
                infographic: imageResponse.suggestions,
                poster: imageResponse.suggestions
            }
        }
    }
}

export const mediaService = new MediaService()
