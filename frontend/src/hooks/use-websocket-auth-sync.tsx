import { useEffect } from 'react'
import { ACCESS_TOKEN } from '@/constants/auth'
import { useWebSocketContext } from '@/contexts/websocket-context'

/**
 * Hook that monitors auth token changes and reconnects the WebSocket
 * when a new token becomes available (e.g. login from another tab, token refresh).
 *
 * The initial connection is owned by SocketIOProvider on mount.
 * Auto-reconnection on disconnect is handled by Socket.IO's built-in reconnection.
 * This hook only covers the case where the token itself changes.
 */
export function useWebSocketAuthSync() {
    const { connectSocket, socket } = useWebSocketContext()

    useEffect(() => {
        // Detect token changes from other browser tabs
        const handleStorageChange = (e: StorageEvent) => {
            if (e.key === ACCESS_TOKEN && e.newValue && !socket?.connected) {
                console.log('WebSocket: Token changed via storage event, reconnecting...')
                connectSocket()
            }
        }

        // Detect token set in the same tab (e.g. after login or token refresh)
        const handleAuthTokenSet = () => {
            const token = localStorage.getItem(ACCESS_TOKEN)
            if (token && !socket?.connected) {
                console.log('WebSocket: Auth token set event, reconnecting...')
                connectSocket()
            }
        }

        window.addEventListener('storage', handleStorageChange)
        window.addEventListener('auth-token-set', handleAuthTokenSet)
        return () => {
            window.removeEventListener('storage', handleStorageChange)
            window.removeEventListener('auth-token-set', handleAuthTokenSet)
        }
    }, [connectSocket, socket?.connected])
}