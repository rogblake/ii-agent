import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

import { sessionService } from '@/services/session.service'
import { ISession } from '@/typings/agent'
import { setActiveSessionId, useAppDispatch } from '@/state'
import SlidesResult from '@/components/agent/slides-result'
import { Icon } from '@/components/ui/icon'
import { Button } from '@/components/ui/button'
import { Logo } from '@/components/logo'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

interface SlideContent {
    slideNumber: number
    content: string
    isImageSlide?: boolean
    imageUrl?: string
}

export function PresentationsPage() {
    const { t } = useTranslation()
    const { sessionId } = useParams()
    const navigate = useNavigate()
    const dispatch = useAppDispatch()
    const isSage = useIsSageTheme()

    const [session, setSession] = useState<ISession | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [presentationData, setPresentationData] = useState<{
        name: string
        slideCount: number
    } | null>(null)
    const [triggerFullscreen, setTriggerFullscreen] = useState(false)
    const [slides, setSlides] = useState<SlideContent[]>([])
    const [activeSlideIndex, setActiveSlideIndex] = useState(0)
    const [scrollToSlide, setScrollToSlide] = useState<number | undefined>(
        undefined
    )
    const [fullscreenStartIndex, setFullscreenStartIndex] = useState<number>(0)

    const handleSlidesLoad = useCallback((loadedSlides: SlideContent[]) => {
        setSlides(loadedSlides)
    }, [])

    const handleThumbnailClick = (index: number) => {
        setScrollToSlide(index)
        setActiveSlideIndex(index)
        // Reset after a short delay to allow re-triggering
        setTimeout(() => setScrollToSlide(undefined), 100)
    }

    const handleActiveSlideChange = (index: number) => {
        setActiveSlideIndex(index)
    }

    useEffect(() => {
        const fetchSession = async () => {
            if (!sessionId) {
                setError(t('presentations.sessionIdNotProvided'))
                setIsLoading(false)
                return
            }

            try {
                const data = await sessionService.getPublicSession(sessionId)

                if (!data) {
                    setError(t('presentations.sessionNotFound'))
                    setIsLoading(false)
                    return
                }

                if (
                    data.agent_type !== 'slide' &&
                    data.agent_type !== 'slide_nano_banana'
                ) {
                    setError(t('presentations.noPresentationInSession'))
                    setIsLoading(false)
                    return
                }

                setSession(data)
                dispatch(setActiveSessionId(sessionId))
                setError(null)
            } catch (err) {
                console.error('Error fetching session:', err)
                if (err && typeof err === 'object' && 'response' in err) {
                    const axiosError = err as { response: { status: number } }
                    if (axiosError.response?.status === 404) {
                        setError(t('presentations.presentationNotFound'))
                    } else {
                        setError(t('presentations.failedToLoad'))
                    }
                } else {
                    setError(t('presentations.failedToLoad'))
                }
            } finally {
                setIsLoading(false)
            }
        }

        fetchSession()
    }, [dispatch, sessionId, t])

    if (isLoading) {
        return (
            <div className="flex h-screen items-center justify-center bg-white dark:bg-charcoal">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white mx-auto mb-2" />
                    <p className="text-black dark:text-white">
                        {t('common.loading')}
                    </p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="flex h-screen items-center justify-center bg-white dark:bg-charcoal">
                <div className="text-center">
                    <Icon
                        name="warning"
                        className="size-16 fill-gray-400 mx-auto mb-4"
                    />
                    <h1 className="text-2xl font-semibold text-black dark:text-white mb-2">
                        {error}
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mb-6">
                        {t('presentations.notAccessible')}
                    </p>
                    <button
                        onClick={() => navigate(-1)}
                        className="px-6 py-3 bg-firefly dark:bg-sky-blue text-sky-blue dark:text-black rounded-lg font-medium hover:opacity-80 transition-opacity"
                    >
                        {t('common.goBack')}
                    </button>
                </div>
            </div>
        )
    }

    if (!session) {
        return null
    }

    const handleSlideshowFromBeginning = () => {
        setFullscreenStartIndex(0)
        setTriggerFullscreen(true)
    }

    const handleSlideshowFromCurrent = () => {
        setFullscreenStartIndex(activeSlideIndex)
        setTriggerFullscreen(true)
    }

    const handleFullscreenTriggered = () => {
        setTriggerFullscreen(false)
    }

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
                    {presentationData?.name || session.name}
                </h1>
            </header>
            <main className="flex-1 overflow-hidden flex px-4">
                {/* Slide Thumbnails Sidebar */}
                <aside className="hidden md:block w-[200px] flex-shrink-0 bg-firefly dark:bg-sky-blue/10 rounded-xl overflow-y-auto p-4">
                    <div className="flex flex-col gap-4">
                        {slides.map((slide, index) => (
                            <div
                                key={slide.slideNumber}
                                className="flex flex-col gap-1"
                            >
                                <div className="text-xs font-bold px-2 py-0.5 bg-sky-blue text-black rounded-full w-fit">
                                    {index + 1} / {slides.length}
                                </div>
                                {(() => {
                                    const iframeContent =
                                        slide.content?.trim() || ''
                                    const hasContent = iframeContent.length > 0

                                    return (
                                        <button
                                            onClick={() =>
                                                handleThumbnailClick(index)
                                            }
                                            className={cn(
                                                'relative w-full aspect-[16/9] rounded-lg overflow-hidden border-5 transition-all cursor-pointer hover:opacity-90',
                                                activeSlideIndex === index
                                                    ? 'border-sky-blue'
                                                    : 'border-transparent'
                                            )}
                                        >
                                            {hasContent ? (
                                                <iframe
                                                    srcDoc={iframeContent}
                                                    className="w-[1280px] h-[720px] origin-top-left scale-[0.13] pointer-events-none bg-black"
                                                    title={t(
                                                        'presentations.slideTitle',
                                                        {
                                                            number: slide.slideNumber
                                                        }
                                                    )}
                                                />
                                            ) : (
                                                <div className="w-full h-full flex items-center justify-center bg-white text-xs text-gray-500">
                                                    {t(
                                                        'presentations.noPreview'
                                                    )}
                                                </div>
                                            )}
                                        </button>
                                    )
                                })()}
                            </div>
                        ))}
                    </div>
                </aside>

                {/* Main Slides View */}
                <div className="flex-1 overflow-hidden relative">
                    <SlidesResult
                        hideHeader
                        readOnly
                        onPresentationDataLoad={setPresentationData}
                        externalFullscreenTrigger={triggerFullscreen}
                        onFullscreenTriggered={handleFullscreenTriggered}
                        slideViewerClassName="!max-h-[calc(100vh-61px)]"
                        onSlidesLoad={handleSlidesLoad}
                        activeSlideIndex={scrollToSlide}
                        onActiveSlideChange={handleActiveSlideChange}
                        fullscreenStartIndex={fullscreenStartIndex}
                    />
                    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10">
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button className="flex items-center gap-2 bg-sky-blue text-black font-medium px-4 py-2 rounded-full hover:opacity-90 transition-opacity shadow-btn">
                                    <Icon
                                        name="play"
                                        className="size-5 stroke-black"
                                    />
                                    {t('presentations.slideshow')}
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent
                                align="center"
                                side="top"
                                sideOffset={8}
                            >
                                <DropdownMenuItem
                                    onClick={handleSlideshowFromBeginning}
                                    className="flex items-center gap-2 cursor-pointer"
                                >
                                    <Icon
                                        name="play"
                                        className="size-5 stroke-black"
                                    />
                                    {t('presentations.playFromBeginning')}
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                    onClick={handleSlideshowFromCurrent}
                                    className="flex items-center gap-2 cursor-pointer"
                                >
                                    <Icon
                                        name="play"
                                        className="size-5 stroke-black"
                                    />
                                    {t('presentations.playFromCurrent')}
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                </div>
            </main>
        </div>
    )
}

export const Component = PresentationsPage
