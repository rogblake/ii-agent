import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import { StorybookProvider, useStorybook } from '@/contexts/storybook-context'
import { StorybookModal } from '@/components/ui/storybook-modal'
import { Icon } from '@/components/ui/icon'
import { Button } from '@/components/ui/button'
import { Logo } from '@/components/logo'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

function StorybookShareContent() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const { storybookId } = useParams()
    const isSage = useIsSageTheme()
    const { loadPublicStorybook, currentStorybook, isLoading, error } =
        useStorybook()
    const [localError, setLocalError] = useState<string | null>(null)

    useEffect(() => {
        const loadStorybook = async () => {
            if (!storybookId) {
                setLocalError(t('storybook.share.storybookIdNotProvided'))
                return
            }

            try {
                await loadPublicStorybook(storybookId)
                setLocalError(null)
            } catch (err) {
                if (err && typeof err === 'object' && 'response' in err) {
                    const axiosError = err as { response?: { status?: number } }
                    if (axiosError.response?.status === 404) {
                        setLocalError(t('storybook.share.storybookNotFound'))
                        return
                    }
                }
                setLocalError(t('storybook.share.failedToLoad'))
            }
        }

        void loadStorybook()
    }, [loadPublicStorybook, storybookId, t])

    const displayError = localError || error

    return (
        <div className="flex flex-col h-screen bg-white dark:bg-charcoal">
            <header className="flex items-center justify-between px-4 py-3">
                <div className="flex gap-x-4 items-center flex-shrink-0">
                    <Logo
                        className="gap-x-[6px]"
                        imageClassName={`${isSage ? '!h-6 md:!h-6' : 'size-6'} inline`}
                        label="II-Agent"
                        labelClassName="text-black dark:text-white text-sm font-semibold"
                    />
                    <Button
                        onClick={() => navigate('/')}
                        className="flex items-center gap-2 bg-sky-blue text-black font-medium px-4 py-2 rounded-full hover:opacity-90 transition-opacity"
                    >
                        <Icon name="ai-magic" className="size-5 stroke-black" />
                        {t('presentations.createYourOwn')}
                    </Button>
                </div>
                <h1 className="text-lg font-semibold text-black dark:text-white line-clamp-1 text-center flex-1">
                    {currentStorybook?.name || t('storybook.viewer.title')}
                </h1>
            </header>
            <main className="flex-1 overflow-hidden flex px-4">
                {isLoading && (
                    <div className="flex h-full w-full items-center justify-center">
                        <div className="text-center">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white mx-auto mb-2" />
                            <p className="text-black dark:text-white">
                                {t('common.loading')}
                            </p>
                        </div>
                    </div>
                )}
                {!isLoading && displayError && (
                    <div className="flex h-full w-full items-center justify-center">
                        <div className="text-center">
                            <Icon
                                name="warning"
                                className="size-16 fill-gray-400 mx-auto mb-4"
                            />
                            <h1 className="text-2xl font-semibold text-black dark:text-white mb-2">
                                {displayError}
                            </h1>
                            <p className="text-gray-600 dark:text-gray-400 mb-6">
                                {t('storybook.share.notAccessible')}
                            </p>
                            <button
                                onClick={() => navigate(-1)}
                                className="px-6 py-3 bg-firefly dark:bg-sky-blue text-sky-blue dark:text-black rounded-lg font-medium hover:opacity-80 transition-opacity"
                            >
                                {t('common.goBack')}
                            </button>
                        </div>
                    </div>
                )}
                {!isLoading && !displayError && (
                    <div className="flex-1 overflow-hidden">
                        <StorybookModal isShareMode publicView />
                    </div>
                )}
            </main>
        </div>
    )
}

export function StorybooksPage() {
    return (
        <StorybookProvider>
            <StorybookShareContent />
        </StorybookProvider>
    )
}

export const Component = StorybooksPage
