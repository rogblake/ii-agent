import axiosInstance from '@/lib/axios'

export interface ConnectorAuthUrlResponse {
    auth_url: string
    state: string
}

export interface ConnectorStatusResponse {
    is_connected: boolean
    connector_type: string
    metadata?: Record<string, unknown>
    access_token?: string
}

export interface GoogleDriveCallbackRequest {
    code: string
    state: string
}

export interface GoogleDriveFilePickRequest {
    file_ids: string[]
}

export interface DownloadedFile {
    id: string
    name: string
    size: number
    mime_type: string
    file_url?: string
    is_folder?: boolean
    file_ids?: number[]
    file_count?: number
}

export interface GoogleDriveFilesResponse {
    success: boolean
    files: DownloadedFile[]
}

export interface GoogleDrivePickerConfigResponse {
    is_connected: boolean
    access_token?: string
    developer_key?: string
    app_id?: string
}

export interface GitHubAppConfigResponse {
    app_name: string | null
    installation_url: string | null
}

export interface GitHubRepository {
    id: number
    name: string
    full_name: string
    owner: string
    private: boolean
    description?: string
    html_url: string
    default_branch: string
}

export interface GitHubRepositoriesResponse {
    repositories: GitHubRepository[]
}

class ConnectorService {
    getGitHubRedirectUri(): string {
        return `${window.location.origin}/auth/oauth/github/callback`
    }

    getRevenueCatRedirectUri(): string {
        return `${window.location.origin}/auth/oauth/revenuecat/callback`
    }

    async getGitHubAuthUrl(): Promise<ConnectorAuthUrlResponse> {
        const redirectUri = this.getGitHubRedirectUri()
        const response = await axiosInstance.get<ConnectorAuthUrlResponse>(
            '/connectors/github/auth-url',
            {
                params: { redirect_uri: redirectUri }
            }
        )
        return response.data
    }

    async handleGitHubCallback(
        code: string,
        state: string
    ): Promise<{ success: boolean; message: string }> {
        const redirectUri = this.getGitHubRedirectUri()
        const response = await axiosInstance.post<{
            success: boolean
            message: string
        }>('/connectors/github/callback', {
            code,
            state,
            redirect_uri: redirectUri
        })
        return response.data
    }

    async getGitHubStatus(): Promise<ConnectorStatusResponse> {
        const response = await axiosInstance.get<ConnectorStatusResponse>(
            '/connectors/github/status'
        )
        return response.data
    }

    async disconnectGitHub(): Promise<{
        success: boolean
        message: string
    }> {
        const response = await axiosInstance.delete<{
            success: boolean
            message: string
        }>('/connectors/github')
        return response.data
    }

    async getGitHubAppConfig(): Promise<GitHubAppConfigResponse> {
        const response = await axiosInstance.get<GitHubAppConfigResponse>(
            '/connectors/github/app-config'
        )
        return response.data
    }

    async getGitHubRepositories(): Promise<GitHubRepositoriesResponse> {
        const response = await axiosInstance.get<GitHubRepositoriesResponse>(
            '/connectors/github/repositories'
        )
        return response.data
    }

    async getRevenueCatAuthUrl(): Promise<ConnectorAuthUrlResponse> {
        const redirectUri = this.getRevenueCatRedirectUri()
        const response = await axiosInstance.get<ConnectorAuthUrlResponse>(
            '/connectors/revenuecat/auth-url',
            {
                params: { redirect_uri: redirectUri }
            }
        )
        return response.data
    }

    async handleRevenueCatCallback(
        code: string,
        state: string
    ): Promise<{ success: boolean; message: string }> {
        const redirectUri = this.getRevenueCatRedirectUri()
        const response = await axiosInstance.post<{
            success: boolean
            message: string
        }>('/connectors/revenuecat/callback', {
            code,
            state,
            redirect_uri: redirectUri
        })
        return response.data
    }

    async getRevenueCatStatus(): Promise<ConnectorStatusResponse> {
        const response = await axiosInstance.get<ConnectorStatusResponse>(
            '/connectors/revenuecat/status'
        )
        return response.data
    }

    async disconnectRevenueCat(): Promise<{
        success: boolean
        message: string
    }> {
        const response = await axiosInstance.delete<{
            success: boolean
            message: string
        }>('/connectors/revenuecat')
        return response.data
    }

    async getGoogleDriveAuthUrl(): Promise<ConnectorAuthUrlResponse> {
        // Pass frontend URL for OAuth callback redirect
        const frontendUrl = window.location.origin
        const response = await axiosInstance.get<ConnectorAuthUrlResponse>(
            '/connectors/google-drive/auth-url',
            {
                params: { frontend_url: frontendUrl }
            }
        )
        return response.data
    }

    async handleGoogleDriveCallback(
        code: string,
        state: string
    ): Promise<{ success: boolean; message: string }> {
        const response = await axiosInstance.post<{
            success: boolean
            message: string
        }>('/connectors/google-drive/callback', {
            code,
            state
        })
        return response.data
    }

    async getGoogleDriveStatus(): Promise<ConnectorStatusResponse> {
        const response = await axiosInstance.get<ConnectorStatusResponse>(
            '/connectors/google-drive/status'
        )
        return response.data
    }

    async getGoogleDrivePickerConfig(): Promise<GoogleDrivePickerConfigResponse> {
        const response =
            await axiosInstance.get<GoogleDrivePickerConfigResponse>(
                '/connectors/google-drive/picker-config'
            )
        return response.data
    }

    async downloadGoogleDriveFiles(
        fileIds: string[]
    ): Promise<GoogleDriveFilesResponse> {
        const response = await axiosInstance.post<GoogleDriveFilesResponse>(
            '/connectors/google-drive/files',
            { file_ids: fileIds }
        )
        return response.data
    }

    async disconnectGoogleDrive(): Promise<{
        success: boolean
        message: string
    }> {
        const response = await axiosInstance.delete<{
            success: boolean
            message: string
        }>('/connectors/google-drive')
        return response.data
    }

    openAuthPopup(
        authUrl: string,
        _windowTitle?: string
    ): Promise<{ code: string; state: string }> {
        return new Promise((resolve, reject) => {
            const authState = this.getAuthStateConfig(authUrl)

            // Detect if we're on a mobile device
            const isMobile = /iPhone|iPad|iPod|Android/i.test(
                navigator.userAgent
            )

            if (isMobile) {
                // On mobile, use full-page redirect instead of popup
                // Store the current intent in sessionStorage
                sessionStorage.setItem(
                    authState.pendingStorageKey,
                    JSON.stringify({
                        timestamp: Date.now(),
                        returnUrl: window.location.href
                    })
                )

                // Set up message listener before redirect
                const allowedOrigins = new Set<string>([
                    window.location.origin
                ])
                try {
                    const apiUrl = import.meta.env.VITE_API_URL
                    if (apiUrl) {
                        allowedOrigins.add(new URL(apiUrl).origin)
                    }
                } catch (error) {
                    console.warn(
                        'Invalid API URL provided in VITE_API_URL:',
                        error
                    )
                }

                window.addEventListener('message', function handler(event) {
                    if (!allowedOrigins.has(event.origin)) return

                    const data = event.data
                    if (data && data.type === authState.messageType) {
                        window.removeEventListener('message', handler)
                        sessionStorage.removeItem(authState.pendingStorageKey)

                        if (data.error) {
                            const description =
                                typeof data.errorDescription === 'string' &&
                                data.errorDescription.length
                                    ? data.errorDescription
                                    : typeof data.error === 'string'
                                      ? data.error
                                      : 'Authorization failed'
                            reject(new Error(description))
                            return
                        }

                        if (data.code && data.state) {
                            resolve({
                                code: data.code,
                                state: data.state
                            })
                        } else {
                            reject(new Error('Authorization failed'))
                        }
                    }
                })

                // Redirect to auth URL
                window.location.href = authUrl
                return
            }

            // Desktop: open new tab (avoids COOP issues with popups).
            // Communication uses BroadcastChannel since window.opener
            // is unreliable after cross-origin navigation.
            const authTab = window.open(authUrl, '_blank')

            if (!authTab) {
                reject(new Error('Failed to open authorization tab'))
                return
            }

            let channel: BroadcastChannel | null = null
            try {
                channel = new BroadcastChannel(authState.messageType)
            } catch {
                reject(
                    new Error(
                        'BroadcastChannel not supported by this browser'
                    )
                )
                return
            }

            const cleanup = () => {
                channel?.close()
                channel = null
            }

            channel.onmessage = (event) => {
                const data = event.data
                if (!data || data.type !== authState.messageType) return
                cleanup()
                if (data.error) {
                    const description =
                        typeof data.errorDescription === 'string' &&
                        data.errorDescription.length
                            ? data.errorDescription
                            : typeof data.error === 'string'
                              ? data.error
                              : 'Authorization failed'
                    reject(new Error(description))
                    return
                }
                if (data.code && data.state) {
                    resolve({ code: data.code, state: data.state })
                } else {
                    reject(new Error('Authorization failed'))
                }
            }
        })
    }

    private getAuthStateConfig(authUrl: string): {
        pendingStorageKey: string
        messageType: string
    } {
        if (authUrl.includes('github')) {
            return {
                pendingStorageKey: 'github_auth_pending',
                messageType: 'github-auth'
            }
        }

        if (authUrl.includes('revenuecat')) {
            return {
                pendingStorageKey: 'revenuecat_auth_pending',
                messageType: 'revenuecat-auth'
            }
        }

        return {
            pendingStorageKey: 'google_drive_auth_pending',
            messageType: 'google-drive-auth'
        }
    }
}

export const connectorService = new ConnectorService()
