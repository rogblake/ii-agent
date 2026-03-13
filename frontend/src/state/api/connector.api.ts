import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type {
    BaseQueryFn,
    FetchArgs,
    FetchBaseQueryError
} from '@reduxjs/toolkit/query'
import type { ConnectorStatusResponse } from '@/services/connector.service'
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
        // All endpoints in this API are connector-specific
        // 401 errors mean the connector token is invalid, not the user session
        // So we should NOT logout the user
        // The error will be handled by the component to show appropriate message
    }
    return result
}

export const connectorApi = createApi({
    reducerPath: 'connectorApi',
    baseQuery: baseQueryWithReauth,
    tagTypes: ['GoogleDriveStatus', 'GitHubStatus', 'RevenueCatStatus'],
    endpoints: (builder) => ({
        getGoogleDriveStatus: builder.query<ConnectorStatusResponse, void>({
            query: () => '/connectors/google-drive/status',
            providesTags: ['GoogleDriveStatus']
        }),
        getGitHubStatus: builder.query<ConnectorStatusResponse, void>({
            query: () => '/connectors/github/status',
            providesTags: ['GitHubStatus']
        }),
        getRevenueCatStatus: builder.query<ConnectorStatusResponse, void>({
            query: () => '/connectors/revenuecat/status',
            providesTags: ['RevenueCatStatus']
        }),
        disconnectGoogleDrive: builder.mutation<
            { success: boolean; message: string },
            void
        >({
            query: () => ({
                url: '/connectors/google-drive',
                method: 'DELETE'
            }),
            invalidatesTags: ['GoogleDriveStatus']
        }),
        disconnectGitHub: builder.mutation<
            { success: boolean; message: string },
            void
        >({
            query: () => ({
                url: '/connectors/github',
                method: 'DELETE'
            }),
            invalidatesTags: ['GitHubStatus']
        }),
        disconnectRevenueCat: builder.mutation<
            { success: boolean; message: string },
            void
        >({
            query: () => ({
                url: '/connectors/revenuecat',
                method: 'DELETE'
            }),
            invalidatesTags: ['RevenueCatStatus']
        })
    })
})

export const {
    useGetGoogleDriveStatusQuery,
    useGetGitHubStatusQuery,
    useGetRevenueCatStatusQuery,
    useDisconnectGoogleDriveMutation,
    useDisconnectGitHubMutation,
    useDisconnectRevenueCatMutation
} = connectorApi
