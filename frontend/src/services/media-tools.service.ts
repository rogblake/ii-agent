import axiosInstance from '@/lib/axios'
import { type MiniTool } from '@/constants/media-tools'

export class MediaToolsService {
    async listMediaTools(): Promise<MiniTool[]> {
        const response = await axiosInstance.get<MiniTool[]>('/media-tools')
        return response.data
    }

}

export const mediaToolsService = new MediaToolsService()
