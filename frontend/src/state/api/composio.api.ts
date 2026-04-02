import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type {
    BaseQueryFn,
    FetchArgs,
    FetchBaseQueryError
} from '@reduxjs/toolkit/query'
import { ACCESS_TOKEN } from '@/constants/auth'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const baseQuery = fetchBaseQuery({
    baseUrl: API_URL,
    prepareHeaders: (headers) => {
        const token = localStorage.getItem(ACCESS_TOKEN)
        if (token) {
            headers.set('Authorization', `Bearer ${token}`)
        }
        headers.set('Content-Type', 'application/json')
        return headers
    }
})

const baseQueryWithReauth: BaseQueryFn<
    string | FetchArgs,
    unknown,
    FetchBaseQueryError
> = async (args, api, extraOptions) => {
    const result = await baseQuery(args, api, extraOptions)
    if (result.error && result.error.status === 401) {
        // Handle 401 errors appropriately
    }
    return result
}

// Type definitions
export interface CategoryInfo {
    id: string
    name: string
}

export interface ComposioToolkit {
    slug: string
    name: string
    description?: string
    logo?: string
    auth_schemes: string[]
    categories_info: CategoryInfo[]
    tools_count?: number
    app_url?: string
}

export interface ComposioToolkitsResponse {
    success: boolean
    toolkits: ComposioToolkit[]
    categories: CategoryInfo[]
    total_items: number
    total_pages: number
    current_page: number
    next_cursor?: string
    has_more: boolean
    error?: string
}

export interface ComposioProfile {
    id: string
    profile_name: string
    toolkit_slug: string
    toolkit_name: string
    status: string  // Values: 'enable', 'disable', 'disconnected', 'pending'
    is_default: boolean
    enabled_tools: string[]
    created_at: string
    updated_at: string
}

export interface ComposioProfilesResponse {
    success: boolean
    profiles: ComposioProfile[]
    error?: string
}

export interface ConnectToolkitRequest {
    profile_name: string
    initiation_fields?: Record<string, string>
    use_custom_auth?: boolean
    custom_auth_config?: Record<string, string>
}

export interface ConnectToolkitResponse {
    success: boolean
    profile_id: string
    redirect_url?: string
    message: string
    connection_status: string
    error?: string
}

export interface ComposioStatusResponse {
    status: string  // Values: 'enable', 'disable', 'disconnected', 'pending'
    connector_type: string
    toolkit_slug: string
    profiles: ComposioProfile[]
}

export interface ComposioAction {
    name: string
    description: string
    category: string
    read_only: boolean
    parameters: object
    default_enabled?: boolean
}

export interface ComposioActionsResponse {
    success: boolean
    actions: ComposioAction[]
    categories: string[]
}

export interface UpdateToolsRequest {
    enabled_tools: string[]
}

export const composioApi = createApi({
    reducerPath: 'composioApi',
    baseQuery: baseQueryWithReauth,
    tagTypes: ['ComposioToolkits', 'ComposioProfiles', 'ComposioStatus', 'ComposioActions'],
    endpoints: (builder) => ({
        // List all available toolkits
        getComposioToolkits: builder.query<
            ComposioToolkitsResponse,
            { search?: string; category?: string; limit?: number }
        >({
            query: ({ search, category, limit = 100 }) => {
                const params = new URLSearchParams()
                if (search) params.append('search', search)
                if (category) params.append('category', category)
                params.append('limit', limit.toString())
                return `/connectors/composio/toolkits?${params.toString()}`
            },
            providesTags: ['ComposioToolkits']
        }),

        // Get toolkit details
        getToolkitDetails: builder.query<
            { success: boolean; toolkit: ComposioToolkit },
            string
        >({
            query: (toolkitSlug) =>
                `/connectors/composio/toolkits/${toolkitSlug}`
        }),

        // Get user's Composio profiles
        getComposioProfiles: builder.query<ComposioProfilesResponse, void>({
            query: () => '/connectors/composio/profiles',
            providesTags: ['ComposioProfiles']
        }),

        // Get status for a specific toolkit
        getComposioStatus: builder.query<ComposioStatusResponse, string>({
            query: (toolkitSlug) =>
                `/connectors/composio/${toolkitSlug}/status`,
            providesTags: (_result, _error, toolkitSlug) => [
                { type: 'ComposioStatus', id: toolkitSlug }
            ]
        }),

        // Connect a toolkit
        connectToolkit: builder.mutation<
            ConnectToolkitResponse,
            { toolkitSlug: string; request: ConnectToolkitRequest }
        >({
            query: ({ toolkitSlug, request }) => ({
                url: `/connectors/composio/${toolkitSlug}/connect`,
                method: 'POST',
                body: request
            }),
            invalidatesTags: ['ComposioProfiles', 'ComposioStatus']
        }),

        // Disconnect a toolkit
        disconnectToolkit: builder.mutation<
            { success: boolean; message: string },
            { toolkitSlug: string; profileId?: string }
        >({
            query: ({ toolkitSlug, profileId }) => {
                const params = profileId
                    ? `?profile_id=${profileId}`
                    : ''
                return {
                    url: `/connectors/composio/${toolkitSlug}${params}`,
                    method: 'DELETE'
                }
            },
            invalidatesTags: ['ComposioProfiles', 'ComposioStatus']
        }),

        // Delete a profile
        deleteProfile: builder.mutation<
            { success: boolean; message: string },
            string
        >({
            query: (profileId) => ({
                url: `/connectors/composio/profiles/${profileId}`,
                method: 'DELETE'
            }),
            invalidatesTags: ['ComposioProfiles', 'ComposioStatus']
        }),

        // Sync profile to agent
        syncProfileToAgent: builder.mutation<
            { success: boolean; mcp_setting_id: string; message: string },
            string
        >({
            query: (profileId) => ({
                url: `/connectors/composio/profiles/${profileId}/sync-to-agent`,
                method: 'POST'
            })
        }),

        // Get toolkit actions
        getToolkitActions: builder.query<ComposioActionsResponse, string>({
            query: (toolkitSlug) =>
                `/connectors/composio/toolkits/${toolkitSlug}/actions`,
            providesTags: (_result, _error, toolkitSlug) => [
                { type: 'ComposioActions', id: toolkitSlug }
            ]
        }),

        // Update profile tools
        updateProfileTools: builder.mutation<
            { success: boolean; message: string },
            { profileId: string; enabledTools: string[] }
        >({
            query: ({ profileId, enabledTools }) => ({
                url: `/connectors/composio/profiles/${profileId}/tools`,
                method: 'PUT',
                body: { enabled_tools: enabledTools }
            }),
            invalidatesTags: ['ComposioProfiles']
        }),

        // Enable profile
        enableProfile: builder.mutation<
            { success: boolean; message: string },
            string
        >({
            query: (profileId) => ({
                url: `/connectors/composio/profiles/${profileId}/enable`,
                method: 'POST'
            }),
            invalidatesTags: ['ComposioProfiles', 'ComposioStatus']
        }),

        // Disable profile
        disableProfile: builder.mutation<
            { success: boolean; message: string },
            string
        >({
            query: (profileId) => ({
                url: `/connectors/composio/profiles/${profileId}/disable`,
                method: 'POST'
            }),
            invalidatesTags: ['ComposioProfiles', 'ComposioStatus']
        }),

        // Complete OAuth flow
        completeOAuth: builder.mutation<
            { success: boolean; message: string },
            { status: string; connectedAccountId: string; appName: string }
        >({
            query: (body) => ({
                url: '/connectors/composio/oauth-complete',
                method: 'POST',
                body
            }),
            invalidatesTags: ['ComposioProfiles', 'ComposioStatus']
        })
    })
})

export const {
    useGetComposioToolkitsQuery,
    useGetToolkitDetailsQuery,
    useGetComposioProfilesQuery,
    useGetComposioStatusQuery,
    useConnectToolkitMutation,
    useDisconnectToolkitMutation,
    useDeleteProfileMutation,
    useSyncProfileToAgentMutation,
    useGetToolkitActionsQuery,
    useUpdateProfileToolsMutation,
    useEnableProfileMutation,
    useDisableProfileMutation,
    useCompleteOAuthMutation
} = composioApi
