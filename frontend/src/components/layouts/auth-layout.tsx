import { Link, Outlet } from 'react-router'
import { useAuth } from '@/contexts/auth-context'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { ENABLE_BETA } from '@/constants/features'
import { useTranslation } from 'react-i18next'
import { Logo } from '@/components/logo'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

export function AuthLayout() {
    const { t } = useTranslation()
    const { isAuthenticated } = useAuth()
    const navigate = useNavigate()
    const isSage = useIsSageTheme()

    useEffect(() => {
        if (isAuthenticated) {
            navigate('/')
        }
    }, [isAuthenticated, navigate])

    return (
        <div className="flex flex-col h-screen justify-between px-3 md:px-6 pt-8 pb-12 overflow-auto">
            <Link to="/" className="flex items-center gap-x-2 md:gap-x-3">
                <Logo
                    className="gap-x-2 md:gap-x-3"
                    imageClassName={`${isSage ? '!h-8 md:!h-10' : 'size-8 md:size-10'} inline`}
                    alt={t('publicHome.logoAlt')}
                    label={t('common.appName')}
                    labelClassName="text-black dark:text-white text-lg md:text-2xl font-semibold"
                    labelWrapperClassName="relative"
                    showBeta={ENABLE_BETA}
                    betaLabel={t('common.beta')}
                />
            </Link>
            <div className="flex-1">
                <Outlet />
            </div>
            <div className="flex justify-center gap-x-10">
                <Link
                    to="/terms"
                    className="dark:text-white text-sm font-semibold hover:underline"
                >
                    {t('publicHome.termsOfUse')}
                </Link>
                <Link
                    to="/privacy"
                    className="dark:text-white text-sm font-semibold hover:underline"
                >
                    {t('publicHome.privacyPolicy')}
                </Link>
            </div>
        </div>
    )
}
