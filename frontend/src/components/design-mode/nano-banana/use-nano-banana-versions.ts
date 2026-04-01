/**
 * Hook for managing slide version history in nano banana design mode.
 * Provides version loading, tracking, and revert functionality.
 */

import { useState, useCallback, useEffect } from 'react'
import axiosInstance from '@/lib/axios'
import type { SlideVersionInfo } from './types'

interface UseNanoBananaVersionsOptions {
    sessionId: string
    presentationName: string
    slideNumber: number
}

export function useNanoBananaVersions({
    sessionId,
    presentationName,
    slideNumber
}: UseNanoBananaVersionsOptions) {
    const [versions, setVersions] = useState<SlideVersionInfo[]>([])
    const [currentVersionId, setCurrentVersionId] = useState<string | null>(
        null
    )
    const [isLoading, setIsLoading] = useState(false)
    const [isReverting, setIsReverting] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const loadVersions = useCallback(async () => {
        if (!sessionId || !presentationName || !slideNumber) return

        setIsLoading(true)
        setError(null)

        try {
            const response = await axiosInstance.get(
                '/v1/slides/nano-banana/versions',
                {
                    params: {
                        session_id: sessionId,
                        presentation_name: presentationName,
                        slide_number: slideNumber
                    }
                }
            )

            setVersions(response.data?.versions || [])
            setCurrentVersionId(response.data?.current_version_id || null)
        } catch (err) {
            const errorMsg =
                err instanceof Error ? err.message : 'Failed to load versions'
            setError(errorMsg)
        } finally {
            setIsLoading(false)
        }
    }, [sessionId, presentationName, slideNumber])

    // Load versions on mount and when slide changes
    useEffect(() => {
        void loadVersions()
    }, [loadVersions])

    const revertToVersion = useCallback(
        async (targetVersionId: string) => {
            if (!sessionId || !presentationName || !slideNumber) return null

            setIsReverting(true)
            setError(null)

            try {
                const response = await axiosInstance.post(
                    '/v1/slides/nano-banana/revert',
                    {
                        session_id: sessionId,
                        presentation_name: presentationName,
                        slide_number: slideNumber,
                        target_version_id: targetVersionId
                    }
                )

                if (response.data?.success) {
                    // Reload versions to get updated list
                    await loadVersions()
                    return response.data.new_image_url
                } else {
                    throw new Error(response.data?.error || 'Revert failed')
                }
            } catch (err) {
                const errorMsg =
                    err instanceof Error ? err.message : 'Failed to revert'
                setError(errorMsg)
                return null
            } finally {
                setIsReverting(false)
            }
        },
        [sessionId, presentationName, slideNumber, loadVersions]
    )

    const currentVersion = versions.find((v) => v.id === currentVersionId)
    const hasMultipleVersions = versions.length > 1

    return {
        versions,
        currentVersionId,
        currentVersion,
        hasMultipleVersions,
        isLoading,
        isReverting,
        error,
        loadVersions,
        revertToVersion
    }
}
