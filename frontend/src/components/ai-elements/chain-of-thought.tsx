'use client'

import { useControllableState } from '@radix-ui/react-use-controllable-state'
import { Badge } from '@/components/ui/badge'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { DotIcon, Loader2, type LucideIcon } from 'lucide-react'
import type { ComponentProps } from 'react'
import { createContext, memo, useContext, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../ui/icon'
import { Shimmer } from './shimmer'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { StorybookProgressUI } from '@/components/storybook-progress-ui'
import type { StorybookProgressData } from '@/utils/storybook-progress'
import { useMediaModels } from '@/hooks/use-media-models'

type ChainOfThoughtContextValue = {
    isOpen: boolean
    setIsOpen: (open: boolean) => void
    isStreaming: boolean
}

const ChainOfThoughtContext = createContext<ChainOfThoughtContextValue | null>(
    null
)

const useChainOfThought = () => {
    const context = useContext(ChainOfThoughtContext)
    if (!context) {
        throw new Error(
            'ChainOfThought components must be used within ChainOfThought'
        )
    }
    return context
}

export type ChainOfThoughtProps = ComponentProps<'div'> & {
    open?: boolean
    defaultOpen?: boolean
    onOpenChange?: (open: boolean) => void
    isStreaming?: boolean
}

export const ChainOfThought = memo(
    ({
        className,
        open,
        defaultOpen = false,
        onOpenChange,
        isStreaming = false,
        children,
        ...props
    }: ChainOfThoughtProps) => {
        const [isOpen, setIsOpen] = useControllableState({
            prop: open,
            defaultProp: defaultOpen,
            onChange: onOpenChange
        })

        const chainOfThoughtContext = useMemo(
            () => ({ isOpen, setIsOpen, isStreaming }),
            [isOpen, setIsOpen, isStreaming]
        )

        return (
            <ChainOfThoughtContext.Provider value={chainOfThoughtContext}>
                <div
                    className={cn('not-prose max-w-prose space-y-4', className)}
                    {...props}
                >
                    {children}
                </div>
            </ChainOfThoughtContext.Provider>
        )
    }
)

export type ChainOfThoughtHeaderProps = ComponentProps<
    typeof CollapsibleTrigger
> & {
    chatMediaMetadata?: Record<string, any>
    hasGenerateImageToolCall?: boolean
    hasGenerateStorybookToolCall?: boolean
    hasGenerateVideoToolCall?: boolean
    storybookProgressData?:
        | (StorybookProgressData & { generatingPages?: number[] })
        | null
    isStorybookCompleted?: boolean
}

export const ChainOfThoughtHeader = memo(
    ({
        className,
        children,
        chatMediaMetadata,
        hasGenerateImageToolCall = false,
        hasGenerateStorybookToolCall = false,
        hasGenerateVideoToolCall = false,
        storybookProgressData,
        isStorybookCompleted = false,
        ...props
    }: ChainOfThoughtHeaderProps) => {
        const { t } = useTranslation()
        const { isOpen, setIsOpen, isStreaming } = useChainOfThought()
        const isSage = useIsSageTheme()
        const { allMediaModels } = useMediaModels()

        // Extract media model info from chatMediaMetadata
        const modelName = chatMediaMetadata?.modelName as string | undefined
        const modelType = chatMediaMetadata?.modelType as string | undefined
        const modelId = chatMediaMetadata?.modelId as string | undefined

        const showModelIcon = useMemo(() => {
            if (!modelId) return 'gallery'
            const matchedModel = allMediaModels.find(
                (model) => model.model_name === modelId || model.id === modelId
            )
            return matchedModel?.icon || 'gallery'
        }, [modelId])

        const labelMap: Record<string, string> = {
            image: t('chainOfThought.status.imageGenerating'),
            infographic: t('chainOfThought.status.infographicGenerating'),
            poster: t('chainOfThought.status.posterGenerating'),
            video: t('chainOfThought.status.videoGenerating'),
            storybook: t('chainOfThought.status.storybookGenerating')
        }
        const showModelGenerating =
            labelMap[modelType as string] ??
            t('chainOfThought.status.modelGenerating')

        const shouldShowStorybookProgress =
            hasGenerateStorybookToolCall &&
            storybookProgressData &&
            (isStreaming ||
                storybookProgressData.progressStatus !== 'completed')

        const shouldShowImageGenerating = useMemo(() => {
            return (
                isStreaming &&
                (modelType === 'image' ||
                    modelType === 'infographic' ||
                    modelType === 'poster') &&
                hasGenerateImageToolCall
            )
        }, [isStreaming, modelType, hasGenerateImageToolCall])

        const shouldShowVideoGenerating = useMemo(
            () =>
                isStreaming &&
                modelType === 'video' &&
                hasGenerateVideoToolCall,
            [isStreaming, modelType, hasGenerateVideoToolCall]
        )

        return (
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    {modelName && (
                        <div className="flex h-7 items-center gap-2 rounded-full bg-firefly px-3 text-sm font-semibold leading-none text-sky-blue-2 shadow-sm dark:bg-white dark:text-black">
                            {showModelIcon && (
                                <Icon
                                    name={showModelIcon}
                                    className="size-4 flex-shrink-0 stroke-black"
                                />
                            )}
                            <span className="max-w truncate hidden md:inline">
                                {modelName}
                            </span>
                        </div>
                    )}
                    <Collapsible
                        className={cn({ 'mb-0': !isOpen })}
                        onOpenChange={setIsOpen}
                        open={isOpen}
                    >
                        <CollapsibleTrigger
                            className={cn(
                                'flex h-7 w-fit items-center gap-2 rounded-full bg-blue-gradient px-3 text-sm font-semibold leading-none text-black shadow-sm transition hover:brightness-95 dark:bg-blue-gradient dark:text-black',
                                className
                            )}
                            {...props}
                        >
                            <Icon name="brain" className="size-4" />
                            <span className="flex-1 text-left">
                                {children ??
                                    (isStreaming ? (
                                        <Shimmer
                                            style={{
                                                backgroundImage:
                                                    'linear-gradient(90deg, #000000 0%, #000000 40%, #ffffff 50%, #000000 60%, #000000 100%)'
                                            }}
                                            duration={1}
                                        >
                                            {t('chainOfThought.thinking', {
                                                appName: isSage ? 'SAGE' : 'II'
                                            })}
                                        </Shimmer>
                                    ) : (
                                        t('chainOfThought.label')
                                    ))}
                            </span>
                            <Icon
                                name="arrow-down"
                                className={cn(
                                    'size-4 transition-transform fill-black/80 dark:fill-black/80',
                                    isOpen ? 'rotate-0' : '-rotate-90'
                                )}
                            />
                        </CollapsibleTrigger>
                    </Collapsible>
                </div>

                {shouldShowStorybookProgress && storybookProgressData ? (
                    <div className="mt-3 w-full">
                        <StorybookProgressUI
                            data={storybookProgressData}
                            generatingPages={
                                storybookProgressData.generatingPages ?? []
                            }
                        />
                    </div>
                ) : shouldShowImageGenerating || shouldShowVideoGenerating ? (
                    // Image generation shimmer box
                    <div className="flex">
                        <div className="relative flex aspect-square w-[360px] items-center justify-center overflow-hidden rounded-2xl text-white shadow-btn bg-blue-gradient">
                            <span className="text-base font-semibold leading-relaxed text-black">
                                <Shimmer
                                    style={{
                                        backgroundImage:
                                            'linear-gradient(90deg, #000000 0%, #000000 40%, #ffffff 50%, #000000 60%, #000000 100%)'
                                    }}
                                    duration={1}
                                >
                                    {showModelGenerating}
                                </Shimmer>
                            </span>
                        </div>
                    </div>
                ) : null}
            </div>
        )
    }
)

export type ChainOfThoughtStepProps = ComponentProps<'div'> & {
    icon?: LucideIcon
    label: string
    description?: string
    status?: 'complete' | 'active' | 'pending'
}

export const ChainOfThoughtStep = memo(
    ({
        className,
        icon: Icon = DotIcon,
        label,
        description,
        status = 'complete',
        children,
        ...props
    }: ChainOfThoughtStepProps) => {
        const statusStyles = {
            complete: 'text-black/56 dark:text-grey-2',
            active: 'text-black/56 dark:text-grey-2',
            pending: 'text-black/56 dark:text-grey-2'
        }

        return (
            <div
                className={cn(
                    'flex gap-2 text-sm',
                    statusStyles[status],
                    'fade-in-0 slide-in-from-top-2 animate-in',
                    className
                )}
                {...props}
            >
                <div className="relative mt-0.5">
                    {status === 'active' ? (
                        <Loader2 className="size-4 animate-spin" />
                    ) : (
                        <Icon className="size-4" />
                    )}
                    <div className="-mx-px absolute top-7 bottom-0 left-1/2 w-px bg-black dark:bg-grey-2" />
                </div>
                <div className="flex-1 space-y-2">
                    <div>{label}</div>
                    {description && (
                        <div className="text-xs">{description}</div>
                    )}
                    {children}
                </div>
            </div>
        )
    }
)

export type ChainOfThoughtSearchResultsProps = ComponentProps<'div'>

export const ChainOfThoughtSearchResults = memo(
    ({ className, ...props }: ChainOfThoughtSearchResultsProps) => (
        <div className={cn('flex flex-col gap-2', className)} {...props} />
    )
)

export type ChainOfThoughtSearchResultProps = ComponentProps<typeof Badge>

export const ChainOfThoughtSearchResult = memo(
    ({ className, children, ...props }: ChainOfThoughtSearchResultProps) => (
        <Badge
            className={cn('gap-1 px-2 py-0.5 font-normal text-xs', className)}
            variant="secondary"
            {...props}
        >
            {children}
        </Badge>
    )
)

export type ChainOfThoughtContentProps = ComponentProps<
    typeof CollapsibleContent
>

export const ChainOfThoughtContent = memo(
    ({ className, children, ...props }: ChainOfThoughtContentProps) => {
        const { isOpen } = useChainOfThought()

        return (
            <Collapsible open={isOpen}>
                <CollapsibleContent
                    className={cn(
                        'mt-2 space-y-3',
                        'data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 text-red outline-none data-[state=closed]:animate-out data-[state=open]:animate-in',
                        className
                    )}
                    {...props}
                >
                    {children}
                </CollapsibleContent>
            </Collapsible>
        )
    }
)

export type ChainOfThoughtImageProps = ComponentProps<'div'> & {
    caption?: string
}

export const ChainOfThoughtImage = memo(
    ({ className, children, caption, ...props }: ChainOfThoughtImageProps) => (
        <div className={cn('mt-2 space-y-2', className)} {...props}>
            <div className="relative flex max-h-[22rem] items-center justify-center overflow-hidden rounded-lg bg-muted p-3">
                {children}
            </div>
            {caption && (
                <p className="text-muted-foreground text-xs">{caption}</p>
            )}
        </div>
    )
)

ChainOfThought.displayName = 'ChainOfThought'
ChainOfThoughtHeader.displayName = 'ChainOfThoughtHeader'
ChainOfThoughtStep.displayName = 'ChainOfThoughtStep'
ChainOfThoughtSearchResults.displayName = 'ChainOfThoughtSearchResults'
ChainOfThoughtSearchResult.displayName = 'ChainOfThoughtSearchResult'
ChainOfThoughtContent.displayName = 'ChainOfThoughtContent'
ChainOfThoughtImage.displayName = 'ChainOfThoughtImage'
