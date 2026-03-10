import axiosInstance from '@/lib/axios'
import {
    SessionPinResponse,
    PinActionResponse
} from '@/typings/pin'

class PinService {
    async getPinnedSessions(): Promise<SessionPinResponse> {
        const response = await axiosInstance.get<SessionPinResponse>(
            '/pin/sessions'
        )
        return response.data
    }

    async pinSession(sessionId: string): Promise<PinActionResponse> {
        const response = await axiosInstance.post<PinActionResponse>(
            `/pin/sessions/${sessionId}`
        )
        return response.data
    }

    async unpinSession(sessionId: string): Promise<PinActionResponse> {
        const response = await axiosInstance.delete<PinActionResponse>(
            `/pin/sessions/${sessionId}`
        )
        return response.data
    }
}

export const pinService = new PinService()
