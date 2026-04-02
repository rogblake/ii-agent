import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogClose,
    DialogContent,
    DialogTitle
} from '@/components/ui/dialog'
import { Icon } from '@/components/ui/icon'
import { DialogTrigger } from '@radix-ui/react-dialog'
import { useChatMediaPreference } from '@/hooks/use-chat-media-preference'
import { selectQuestionMode, useAppSelector } from '@/state'
import { QUESTION_MODE } from '@/typings'

const carouselImages = [
    'https://sfile.ii.inc/home/gen-image/1.svg',
    'https://sfile.ii.inc/home/gen-image/2.svg',
    'https://sfile.ii.inc/home/gen-image/3.svg',
    'https://sfile.ii.inc/home/gen-image/4.svg'
]

const carouselVideos = [
    'https://sfile.ii.inc/home/gen-video/1.svg',
    'https://sfile.ii.inc/home/gen-video/2.svg'
]

const carouselStorybook = [
    'https://sfile.ii.inc/home/gen-storybook/1.svg',
    'https://sfile.ii.inc/home/gen-storybook/2.svg',
    'https://sfile.ii.inc/home/gen-storybook/3.svg',
    'https://sfile.ii.inc/home/gen-storybook/4.svg',
    'https://sfile.ii.inc/home/gen-storybook/5.svg',
    'https://sfile.ii.inc/home/gen-storybook/6.svg',
    'https://sfile.ii.inc/home/gen-storybook/7.svg',
    'https://sfile.ii.inc/home/gen-storybook/8.svg',
    'https://sfile.ii.inc/home/gen-storybook/9.svg'
]

interface LearnMoreProps {
    onTry?: () => void
}

export function LearnMore({ onTry }: LearnMoreProps) {
    const { chatMediaPreference } = useChatMediaPreference()
    const questionMode = useAppSelector(selectQuestionMode)
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const mediaType = chatMediaPreference.type
    const carouselItems =
        mediaType === 'video'
            ? carouselVideos
            : mediaType === 'storybook'
              ? carouselStorybook
              : carouselImages
    const translationKey =
        mediaType === 'video'
            ? 'home.learnMoreModal.videoItems'
            : mediaType === 'storybook'
              ? 'home.learnMoreModal.storybookItems'
              : 'home.learnMoreModal.items'

    const rawItems = t(translationKey, {
        returnObjects: true
    }) as unknown
    const items = Array.isArray(rawItems)
        ? (rawItems as Array<{ title: string; description: string }>)
        : []
    const [activeIndex, setActiveIndex] = useState(0)

    useEffect(() => {
        if (!open) return
        setActiveIndex(0)
    }, [open])

    useEffect(() => {
        if (!open) return
        const intervalId = setInterval(() => {
            setActiveIndex((prev) => (prev + 1) % carouselItems.length)
        }, 4500)

        return () => clearInterval(intervalId)
    }, [open, carouselItems.length])

    const handleTry = () => {
        onTry?.()
        setOpen(false)
    }

    if (!chatMediaPreference.enabled || questionMode !== QUESTION_MODE.CHAT)
        return null

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <div className="flex items-center">
                    <Button className="inline md:hidden p-0">
                        <Icon
                            name="info-circle-2"
                            className="size-6 text-orange dark:text-yellow"
                        />
                    </Button>
                    <Button className="hidden md:flex h-7 text-black dark:text-yellow bg-charcoal/10 dark:bg-yellow/10 rounded-full font-normal text-xs">
                        {t('home.learnMoreAboutMediaGenerate')}
                        <Icon
                            name="export"
                            className="fill-black dark:fill-yellow size-4"
                        />
                    </Button>
                </div>
            </DialogTrigger>
            <DialogContent
                showCloseButton={false}
                className="md:max-w-[400px] rounded-[32px] border-0 bg-white dark:bg-charcoal p-0"
                overlayClassName="bg-grey/87 dark:bg-firefly/87"
            >
                <div className="relative overflow-hidden rounded-[32px] px-6 pb-8 pt-6 md:px-10 md:pb-10 md:pt-6">
                    <div className="relative z-10 flex flex-col items-center text-center">
                        <div className="relative w-full">
                            <DialogTitle className="text-center text-lg font-semibold tracking-tight text-black dark:text-white">
                                {t(
                                    mediaType === 'video'
                                        ? 'home.learnMoreModal.videoTitle'
                                        : mediaType === 'storybook'
                                          ? 'home.learnMoreModal.storybookTitle'
                                          : 'home.learnMoreModal.title'
                                )}
                            </DialogTitle>
                            <DialogClose
                                className="absolute cursor-pointer -right-3 md:-right-6 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-full"
                                aria-label={t('common.close')}
                            >
                                <Icon
                                    name="close-2"
                                    className="size-6 text-black dark:text-white"
                                />
                            </DialogClose>
                        </div>

                        <div className="relative mt-9 flex h-[220px] w-full max-w-[320px] items-center justify-center">
                            <div className="w-full">
                                {carouselItems.map((src, index) => (
                                    <img
                                        key={src}
                                        src={src}
                                        alt={t('home.learnMoreModal.imageAlt')}
                                        className={`absolute inset-0 w-full object-cover transition-opacity duration-500 ${
                                            index === activeIndex
                                                ? 'opacity-100'
                                                : 'opacity-0'
                                        }`}
                                        loading="lazy"
                                    />
                                ))}
                            </div>
                        </div>

                        <div>
                            <p className="text-2xl font-semibold text-black dark:text-sky-blue-2">
                                {items[activeIndex]?.title ??
                                    t('home.learnMoreModal.featureTitle')}
                            </p>
                            <p className="mt-2 text-xs leading-relaxed text-black dark:text-white">
                                {items[activeIndex]?.description ??
                                    t('home.learnMoreModal.featureDescription')}
                            </p>
                        </div>

                        <div className="mt-6 flex items-center gap-3">
                            {carouselItems.map((_, index) => (
                                <button
                                    key={`learn-more-dot-${index}`}
                                    type="button"
                                    aria-label={`Slide ${index + 1}`}
                                    onClick={() => setActiveIndex(index)}
                                    className={`size-2.5 rounded-full transition ${
                                        index === activeIndex
                                            ? 'bg-charcoal dark:bg-sky-blue-2'
                                            : 'bg-charcoal/30 dark:bg-sky-blue-2/30'
                                    }`}
                                />
                            ))}
                        </div>

                        <Button
                            size="xl"
                            className="mt-8 h-12 w-full max-w-[320px] rounded-lg bg-sky-blue text-black"
                            onClick={handleTry}
                        >
                            {t('home.learnMoreModal.tryNow')}
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}

export default LearnMore
