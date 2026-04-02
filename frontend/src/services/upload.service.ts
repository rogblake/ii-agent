import axiosInstance from '@/lib/axios'
import {
    GenerateUploadUrlRequest,
    GenerateUploadUrlResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    MediaLibraryResponse
} from '@/typings/upload'

class UploadService {
    async generateUploadUrl(data: GenerateUploadUrlRequest): Promise<GenerateUploadUrlResponse> {
        const response = await axiosInstance.post<GenerateUploadUrlResponse>('/v1/assets/upload', data)
        return response.data
    }

    async uploadComplete(assetId: string, data?: UploadCompleteRequest): Promise<UploadCompleteResponse> {
        const response = await axiosInstance.post<UploadCompleteResponse>(`/v1/assets/${assetId}/complete`, data ?? {})
        return response.data
    }

    async getUserMediaLibrary(params?: { limit?: number; offset?: number }): Promise<MediaLibraryResponse> {
        const response = await axiosInstance.get<MediaLibraryResponse>(
            '/v1/assets/media-library',
            { params }
        )
        return response.data
    }
}

export const uploadService = new UploadService()
