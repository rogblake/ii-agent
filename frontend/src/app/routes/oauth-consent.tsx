import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/auth-context'

interface ConsentData {
    client_name: string
    scope: string
    consent_id: string
}

export function OAuthConsentPage() {
    const [searchParams] = useSearchParams()
    const { user, isAuthenticated, isLoading } = useAuth()
    const [consentData, setConsentData] = useState<ConsentData | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

    // Get consent data from URL params
    useEffect(() => {
        const consentId = searchParams.get('consent_id')
        const clientName = searchParams.get('client_name') || 'ChatGPT'
        const scope = searchParams.get('scope') || 'mcp:tools'

        if (consentId) {
            setConsentData({
                consent_id: consentId,
                client_name: clientName,
                scope: scope
            })
        } else {
            setError('Invalid consent request')
        }
    }, [searchParams])

    // If not authenticated, redirect to login with return URL
    useEffect(() => {
        if (!isLoading && !isAuthenticated) {
            const currentUrl = window.location.href
            const loginUrl = `/login?return_to=${encodeURIComponent(currentUrl)}`
            window.location.href = loginUrl
        }
    }, [isLoading, isAuthenticated])

    const handleConsent = useCallback(
        async (action: 'allow' | 'deny') => {
            if (!consentData) return

            setIsSubmitting(true)
            try {
                // Submit consent decision to backend
                const response = await fetch(
                    `${apiBaseUrl}/mcp/oauth/consent`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded'
                        },
                        body: new URLSearchParams({
                            consent_id: consentData.consent_id,
                            action: action,
                            user_id: user?.id || '',
                            user_email: user?.email || ''
                        })
                    }
                )

                const data = await response.json()

                if (response.ok && data.redirect_url) {
                    // Backend returns redirect URL as JSON to avoid CORS issues
                    // with cross-origin redirects (e.g., to chatgpt.com)
                    window.location.href = data.redirect_url
                } else if (!response.ok) {
                    setError(
                        data.error_description || 'Failed to process consent'
                    )
                }
            } catch (err) {
                console.error('Consent error:', err)
                setError('Failed to process consent')
            } finally {
                setIsSubmitting(false)
            }
        },
        [consentData, apiBaseUrl, user]
    )

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white" />
            </div>
        )
    }

    if (error) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <h1 className="text-2xl font-bold text-red-500 mb-4">
                        Error
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400">{error}</p>
                </div>
            </div>
        )
    }

    if (!consentData) {
        return null
    }

    return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="bg-white dark:bg-firefly rounded-2xl shadow-xl p-8 max-w-md w-full mx-4">
                {/* Logos */}
                <div className="flex items-center justify-center gap-4 mb-8">
                    <img
                        src="https://chat.openai.com/favicon.ico"
                        alt="ChatGPT"
                        className="w-12 h-12 rounded-xl"
                    />
                    <span className="text-gray-400 text-2xl">···</span>
                    <img
                        src="/images/logo-only.png"
                        alt="II"
                        className="size-15 rounded-xl"
                    />
                </div>

                {/* Title */}
                <h1 className="text-xl font-semibold text-center text-gray-900 dark:text-white mb-2">
                    {consentData?.client_name} would like to access your II
                    account
                </h1>

                {/* User info */}
                <p className="text-center text-gray-400 mb-6">
                    {user?.first_name && user?.last_name
                        ? `${user.first_name} ${user.last_name}`
                        : user?.email || 'Logged in user'}
                    {user?.email && user?.first_name && (
                        <span className="block text-sm">{user.email}</span>
                    )}
                </p>

                {/* Permissions */}
                <div className="mb-6">
                    <p className="text-sm text-white mb-3">
                        This app is requesting the following permissions:
                    </p>
                    <div className="space-y-2">
                        <PermissionItem text="Access II-Agent tools" />
                        <PermissionItem text="Create and manage agent sessions" />
                        <PermissionItem text="Generate websites and projects" />
                    </div>
                </div>

                {/* Buttons */}
                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        className="flex-1"
                        onClick={() => handleConsent('deny')}
                        disabled={isSubmitting}
                    >
                        Deny
                    </Button>
                    <Button
                        className="flex-1 bg-sky-blue text-black"
                        onClick={() => handleConsent('allow')}
                        disabled={isSubmitting}
                    >
                        {isSubmitting ? 'Processing...' : 'Allow'}
                    </Button>
                </div>
            </div>
        </div>
    )
}

function PermissionItem({ text }: { text: string }) {
    return (
        <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
            <span className="text-green-500">✓</span>
            <span>{text}</span>
        </div>
    )
}

export const Component = OAuthConsentPage
