import { useEffect, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router'
import { useCompleteOAuthMutation } from '@/state/api/composio.api'

export function ComposioOAuthCallback() {
    const [searchParams] = useSearchParams()
    const navigate = useNavigate()
    const [completeOAuth] = useCompleteOAuthMutation()
    const hasProcessed = useRef(false)

    useEffect(() => {
        // Prevent double execution (React 18 StrictMode, re-renders)
        if (hasProcessed.current) return
        hasProcessed.current = true

        const status = searchParams.get('status')
        const connectedAccountId = searchParams.get('connectedAccountId')
        const appName = searchParams.get('appName')
        const error = searchParams.get('error')

        async function handleOAuthComplete() {
            try {
                if (error || status === 'error') {
                    throw new Error(error || 'OAuth authorization failed')
                }

                if (status === 'success' && connectedAccountId && appName) {
                    // Call authenticated backend endpoint to complete OAuth
                    await completeOAuth({
                        status,
                        connectedAccountId,
                        appName
                    }).unwrap()

                    // Success - OAuth completed
                    // Check if this is a mobile redirect flow
                    const authPendingStr = sessionStorage.getItem('composio_auth_pending')
                    const isMobileRedirect = authPendingStr !== null

                    if (isMobileRedirect) {
                        // Mobile redirect flow - post message to self and navigate back
                        let authData = { returnUrl: '/' }
                        try {
                            authData = JSON.parse(authPendingStr)
                        } catch (parseErr) {
                            console.error('Failed to parse auth pending data:', parseErr)
                        }
                        sessionStorage.removeItem('composio_auth_pending')

                        window.postMessage(
                            {
                                type: 'composio-auth',
                                success: true,
                                appName,
                                connectedAccountId
                            },
                            window.location.origin
                        )

                        // Navigate back to the original URL or home
                        const returnUrl = authData.returnUrl || '/'
                        navigate(returnUrl, { replace: true })
                    } else if (window.opener) {
                        // Desktop popup flow - post message to opener window
                        window.opener.postMessage(
                            {
                                type: 'composio-auth',
                                success: true,
                                appName,
                                connectedAccountId
                            },
                            window.location.origin
                        )
                        window.close()
                    } // else {
                    //     // Fallback: redirect to connectors page
                    //     navigate('/connectors', { replace: true })
                    // }
                } else {
                    throw new Error('Missing required OAuth parameters')
                }
            } catch (err) {
                console.error('OAuth completion error:', err)

                // Check if this is a mobile redirect flow
                const authPendingStr = sessionStorage.getItem('composio_auth_pending')
                const isMobileRedirect = authPendingStr !== null

                if (isMobileRedirect) {
                    let authData = { returnUrl: '/' }
                    try {
                        authData = JSON.parse(authPendingStr)
                    } catch (parseErr) {
                        console.error('Failed to parse auth pending data:', parseErr)
                    }
                    sessionStorage.removeItem('composio_auth_pending')
                    
                    window.postMessage(
                        {
                            type: 'composio-auth',
                            error: err instanceof Error ? err.message : 'Unknown error'
                        },
                        window.location.origin
                    )
                    const returnUrl = authData.returnUrl || '/'
                    navigate(returnUrl, { replace: true })
                } else if (window.opener) {
                    window.opener.postMessage(
                        {
                            type: 'composio-auth',
                            error: err instanceof Error ? err.message : 'Unknown error'
                        },
                        window.location.origin
                    )
                    window.close()
                } else {
                    // Fallback: redirect to connectors page with error
                    navigate('/connectors?error=oauth_failed', { replace: true })
                }
            }
        }

        handleOAuthComplete()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
                <h2 className="text-xl font-semibold mb-2">
                    Composio Authorization
                </h2>
                <p className="text-gray-600">
                    Processing authorization... This window will close
                    automatically.
                </p>
            </div>
        </div>
    )
}
