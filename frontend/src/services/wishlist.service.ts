import axiosInstance from '@/lib/axios'
import {
    SessionWishlistResponse,
    WishlistActionResponse
} from '@/typings/wishlist'

class WishlistService {
    async getWishlistSessions(): Promise<SessionWishlistResponse> {
        const response = await axiosInstance.get<SessionWishlistResponse>(
            '/v1/sessions/wishlist'
        )
        return response.data
    }

    async addToWishlist(sessionId: string): Promise<WishlistActionResponse> {
        const response = await axiosInstance.post<WishlistActionResponse>(
            `/v1/sessions/wishlist/${sessionId}`
        )
        return response.data
    }

    async removeFromWishlist(sessionId: string): Promise<WishlistActionResponse> {
        const response = await axiosInstance.delete<WishlistActionResponse>(
            `/v1/sessions/wishlist/${sessionId}`
        )
        return response.data
    }
}

export const wishlistService = new WishlistService()