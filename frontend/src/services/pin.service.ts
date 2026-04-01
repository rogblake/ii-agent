import axiosInstance from '@/lib/axios'
import {
    SessionPinResponse,
    PinActionResponse
} from '@/typings/pin'

class PinService {
    async getPinnedSessions(): Promise<SessionPinResponse> {
        const response = await axiosInstance.get<SessionPinResponse>(
            '/v1/sessions/pins'
        )
        return response.data
    }

    async pinSession(sessionId: string): Promise<PinActionResponse> {
        const response = await axiosInstance.post<PinActionResponse>(
            `/v1/sessions/pins/${sessionId}`
        )
        return response.data
    }

    async unpinSession(sessionId: string): Promise<PinActionResponse> {
        const response = await axiosInstance.delete<PinActionResponse>(
            `/v1/sessions/pins/${sessionId}`
        )
        return response.data
    }
}

export const pinService = new PinService()
