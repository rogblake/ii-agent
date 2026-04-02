import { Link, useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Logo } from './logo'
import { Button } from './ui/button'
import { Icon } from './ui/icon'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

const PublicHomePage = () => {
    const navigate = useNavigate()
    const { t } = useTranslation()
    const isSage = useIsSageTheme()

    const handleLogin = () => {
        navigate('/login')
    }

    const featureColumns = [
        [
            {
                icon: 'usb',
                title: t('publicHome.features.dataControl.title'),
                description: t('publicHome.features.dataControl.description'),
                highlights: [],
                ctaLabel: ''
            },
            {
                icon: 'presentation',
                title: t('publicHome.features.deck.title'),
                description: t('publicHome.features.deck.description')
            },
            {
                icon: 'bracket-square',
                title: t('publicHome.features.code.title'),
                description: t('publicHome.features.code.description'),
                ctaLabel: ''
            }
        ],
        [
            {
                icon: 'property-search',
                title: t('publicHome.features.research.title'),
                description: t('publicHome.features.research.description'),
                highlights: t('publicHome.features.research.highlights', {
                    returnObjects: true
                }) as string[],
                ctaLabel: ''
            },
            {
                icon: 'ai-browser',
                title: t('publicHome.features.ship.title'),
                description: t('publicHome.features.ship.description'),
                highlights: t('publicHome.features.ship.highlights', {
                    returnObjects: true
                }) as string[],
                ctaLabel: ''
            }
        ]
    ]

    return (
        <div className="flex flex-col h-screen justify-between px-3 md:px-6 pt-4 md:pt-8 pb-12 overflow-auto">
            <Link to="/" className="flex items-center gap-x-3">
                <Logo
                    className="gap-x-3"
                    imageClassName={`${isSage ? '!h-6 md:!h-10' : 'size-10'} inline`}
                    alt={t('publicHome.logoAlt')}
                    label={t('common.appName')}
                    labelClassName="text-black dark:text-white text-2xl font-semibold"
                />
            </Link>
            <div className="flex-1 flex flex-col justify-center items-center mt-8 md:mt-0">
                <p className="text-2xl md:text-[32px] font-semibold text-firefly dark:text-sky-blue">
                    {t('publicHome.heading', {
                        appName: isSage ? 'SAGE' : t('common.appName')
                    })}
                </p>
                {isSage ? (
                    <img
                        src="/images/sage-icon.png"
                        alt="SAGE"
                        className="w-50 md:w-80 mt-2"
                    />
                ) : (
                    <>
                        <img
                            src="/images/agent-head.png"
                            alt={t('publicHome.agentAlt')}
                            className="w-50 md:w-80 mt-2 hidden dark:inline"
                        />
                        <img
                            src="/images/agent-head-light.png"
                            alt={t('publicHome.agentAlt')}
                            className="w-50 md:w-80 mt-2 inline dark:hidden"
                        />
                    </>
                )}

                <p className="text-center mt-6 text-xl md:text-2xl text-firefly dark:text-white">
                    {t('publicHome.tagline')}
                </p>
                <Button
                    onClick={handleLogin}
                    className="mt-6 h-10 md:h-12 px-4 md:px-6 rounded-3xl bg-firefly text-sky-blue dark:bg-sky-blue dark:text-black"
                >
                    {t('publicHome.cta')}
                </Button>
                <div className="mt-12 w-full max-w-5xl">
                    <div className="grid gap-3 md:gap-4 grid-cols-2">
                        {featureColumns.map((column, columnIndex) => (
                            <div
                                key={columnIndex}
                                className="flex flex-col gap-3 md:gap-4"
                            >
                                {column.map(
                                    (
                                        {
                                            icon,
                                            title,
                                            description,
                                            highlights,
                                            ctaLabel
                                        },
                                        featureIndex
                                    ) => (
                                        <div
                                            key={`${title}-${featureIndex}`}
                                            className="group relative overflow-hidden rounded-xl border-2 border-firefly bg-[#0F2B330D] px-3 py-5 md:px-4 shadow-[0_24px_45px_rgba(15,43,51,0.08)] dark:border-sky-blue-3 dark:bg-charcoal dark:text-sky-blue dark:shadow-[0_4px_24px_rgba(255,255,255,0.16)]"
                                        >
                                            <div className="relative flex justify-center h-full flex-col gap-3 md:gap-6">
                                                <div className="flex justify-center">
                                                    <Icon
                                                        name={icon}
                                                        className="size-12 md:size-16 fill-black dark:fill-sky-blue-3"
                                                    />
                                                </div>
                                                <div className="text-center">
                                                    <h3 className="text-base md:text-2xl font-semibold text-black dark:text-white">
                                                        {title}
                                                    </h3>
                                                    <p className="mt-[6px] text-xs md:text-base text-firefly dark:text-grey">
                                                        {description}
                                                    </p>
                                                </div>
                                                {highlights?.length ? (
                                                    <div className="flex flex-wrap justify-center gap-3">
                                                        {highlights.map(
                                                            (item) => (
                                                                <div
                                                                    key={item}
                                                                    className="inline-flex items-center gap-1 md:gap-2 rounded-full border border-firefly px-3 md:px-4 py-1 md:py-1.5 text-[10px] md:text-sm font-semibold text-firefly/90 dark:border-sky-blue-3 dark:text-sky-blue-3"
                                                                >
                                                                    <Icon
                                                                        name="arrow-right-2"
                                                                        className="size-3 fill-firefly dark:fill-sky-blue-3"
                                                                    />
                                                                    <span className="flex-1">
                                                                        {item}
                                                                    </span>
                                                                </div>
                                                            )
                                                        )}
                                                    </div>
                                                ) : null}
                                                {ctaLabel ? (
                                                    <Button
                                                        onClick={handleLogin}
                                                        className="mt-3 h-7 md:h-12 w-fit m-auto rounded-3xl bg-firefly text-sky-blue dark:bg-sky-blue dark:text-black"
                                                    >
                                                        {ctaLabel}
                                                    </Button>
                                                ) : null}
                                            </div>
                                        </div>
                                    )
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            </div>
            <div className="flex justify-center gap-x-10 mt-8 md:mt-12">
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

export default PublicHomePage
