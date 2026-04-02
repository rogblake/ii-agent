import { Link, Outlet } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Logo } from '@/components/logo'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

export function PublicLayout() {
    const { t } = useTranslation()
    const isSage = useIsSageTheme()

    return (
        <div className="flex flex-col h-screen justify-between px-6 pt-8 pb-12 overflow-auto">
            <Link to="/" className="flex items-center gap-x-3">
                <Logo
                    className="gap-x-3"
                    imageClassName={`${isSage ? '!h-6 md:!h-10' : 'size-10'} inline`}
                    alt={t('publicHome.logoAlt')}
                    label={t('common.appName')}
                    labelClassName="text-black dark:text-white text-2xl font-semibold"
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
