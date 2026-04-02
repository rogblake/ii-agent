import { Navigate } from 'react-router'
import { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/contexts/auth-context'

interface ProtectedRouteProps {
    children: ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
    const { isAuthenticated, isLoading } = useAuth()
    const { t } = useTranslation()

    if (isLoading) {
        return (
            <div className="flex h-screen items-center justify-center">
                <div className="text-lg">{t('common.loading')}</div>
            </div>
        )
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />
    }

    return <>{children}</>
}
