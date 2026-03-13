import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

export function RevenueCatCallback() {
    const [searchParams] = useSearchParams()
    const navigate = useNavigate()

    useEffect(() => {
        const code = searchParams.get('code')
        const state = searchParams.get('state')
        const error = searchParams.get('error')
        const errorDescription = searchParams.get('error_description')

        const authPending = sessionStorage.getItem('revenuecat_auth_pending')
        const isMobileRedirect = authPending !== null

        // Build the message payload once
        const message = error
            ? { type: 'revenuecat-auth', error, errorDescription }
            : code && state
              ? { type: 'revenuecat-auth', code, state }
              : null

        if (!message) {
            window.close()
            return
        }

        if (isMobileRedirect) {
            const authData = JSON.parse(authPending)
            sessionStorage.removeItem('revenuecat_auth_pending')
            window.postMessage(message, window.location.origin)
            navigate(authData.returnUrl || '/', { replace: true })
            return
        }

        // Desktop tab/popup: use BroadcastChannel (reliable across
        // cross-origin navigations where window.opener is cleared).
        try {
            const bc = new BroadcastChannel('revenuecat-auth')
            bc.postMessage(message)
            bc.close()
        } catch {
            // Fallback to window.opener if BroadcastChannel is unsupported
            if (window.opener) {
                window.opener.postMessage(message, window.location.origin)
            }
        }
        window.close()
    }, [navigate, searchParams])

    return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
                <h2 className="text-xl font-semibold mb-2">
                    RevenueCat Authorization
                </h2>
                <p className="text-gray-600">
                    Processing authorization... This window will close
                    automatically.
                </p>
            </div>
        </div>
    )
}
