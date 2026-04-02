import { useState, useEffect, useCallback, useMemo } from 'react'
import {
    mediaService,
    type MediaModelsResponse
} from '@/services/media.service'
import type { ChatMediaModel } from '@/constants/media-models'
import type { ChatMediaType } from '@/constants/media-type-config'

interface UseMediaModelsResult {
    imageModels: ChatMediaModel[]
    storybookModels: ChatMediaModel[]
    videoModels: ChatMediaModel[]
    allMediaModels: ChatMediaModel[]
    suggestions: Record<ChatMediaType, string[]>
    isLoading: boolean
    error: Error | null
    refetch: () => Promise<void>
    getModelsForMediaType: (type: ChatMediaType) => ChatMediaModel[]
}

// Empty initial state
const EMPTY_DATA: MediaModelsResponse = {
    imageModels: [],
    storybookModels: [],
    videoModels: [],
    suggestions: { image: [], storybook: [], video: [], infographic: [], poster: [] }
}

// Singleton cache for media models
let cachedModels: MediaModelsResponse | null = null
let fetchPromise: Promise<MediaModelsResponse> | null = null

export function useMediaModels(): UseMediaModelsResult {
    const [data, setData] = useState<MediaModelsResponse>(
        cachedModels ?? EMPTY_DATA
    )
    const [isLoading, setIsLoading] = useState(!cachedModels)
    const [error, setError] = useState<Error | null>(null)

    const fetchModels = useCallback(async () => {
        // Return cached data if available
        if (cachedModels) {
            setData(cachedModels)
            setIsLoading(false)
            return
        }

        // If already fetching, wait for that promise
        if (fetchPromise) {
            try {
                const result = await fetchPromise
                setData(result)
                setError(null)
            } catch (err) {
                setError(
                    err instanceof Error ? err : new Error('Failed to fetch models')
                )
            } finally {
                setIsLoading(false)
            }
            return
        }

        setIsLoading(true)
        setError(null)

        // Create a new fetch promise
        fetchPromise = mediaService.getAllMediaModels()

        try {
            const result = await fetchPromise
            // Only cache if we got actual data - don't cache empty responses from transient failures
            const hasData = result.imageModels.length > 0 ||
                           result.storybookModels.length > 0 ||
                           result.videoModels.length > 0
            if (hasData) {
                cachedModels = result
            }
            setData(result)
            setError(null)
        } catch (err) {
            console.error('Failed to fetch media models:', err)
            setError(
                err instanceof Error ? err : new Error('Failed to fetch models')
            )
        } finally {
            setIsLoading(false)
            fetchPromise = null
        }
    }, [])

    const refetch = useCallback(async () => {
        // Clear cache to force refetch
        cachedModels = null
        fetchPromise = null
        await fetchModels()
    }, [fetchModels])

    useEffect(() => {
        fetchModels()
    }, [fetchModels])

    const getModelsForMediaType = useCallback(
        (type: ChatMediaType): ChatMediaModel[] => {
            switch (type) {
                case 'image':
                    return data.imageModels
                case 'infographic':
                    return data.imageModels
                case 'storybook':
                    return data.storybookModels
                case 'video':
                    return data.videoModels
                case 'poster':
                    return data.imageModels
                default:
                    return []
            }
        },
        [data]
    )

    const allMediaModels = useMemo(
        () => [...data.imageModels, ...data.storybookModels, ...data.videoModels],
        [data.imageModels, data.storybookModels, data.videoModels]
    )

    return {
        imageModels: data.imageModels,
        storybookModels: data.storybookModels,
        videoModels: data.videoModels,
        allMediaModels,
        suggestions: data.suggestions,
        isLoading,
        error,
        refetch,
        getModelsForMediaType
    }
}

// Export a function to clear the cache (useful for testing or when models need to be refreshed)
export function clearMediaModelsCache(): void {
    cachedModels = null
    fetchPromise = null
}
