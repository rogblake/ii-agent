import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronDown, ChevronRight, Copy } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Response } from '@/components/ai-elements/response'
import type { ContentPart } from '@/utils/chat-events'

const PREVIEW_LENGTH = 200

interface ModelCardProps {
    modelId: string
    modelName: string
    content: string
    status: string
    errorMessage?: string
}

function ModelCard({
    modelName,
    content,
    status,
    errorMessage
}: ModelCardProps) {
    const { t } = useTranslation()
    const [isExpanded, setIsExpanded] = useState(false)

    const { preview, canExpand } = useMemo(() => {
        if (!content) return { preview: '', canExpand: false }
        const stripped = content.replace(/[#*`_~>\-|[\]()!]/g, '').trim()
        if (stripped.length <= PREVIEW_LENGTH) return { preview: stripped, canExpand: false }
        return { preview: stripped.slice(0, PREVIEW_LENGTH).trimEnd() + '...', canExpand: true }
    }, [content])

    return (
        <div className="rounded-lg border border-grey-3 dark:border-white/10 bg-white dark:bg-charcoal transition-colors">
            {/* Header + preview (always visible) */}
            <div className="px-3 py-2.5">
                <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-charcoal dark:text-white">
                        {modelName}
                    </span>
                    <div className="flex items-center gap-2">
                        {status === 'streaming' && (
                            <span className="flex items-center gap-1.5 text-xs text-sky-blue dark:text-sky-blue">
                                <span className="relative flex size-2">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-blue opacity-75" />
                                    <span className="relative inline-flex rounded-full size-2 bg-sky-blue" />
                                </span>
                                {t('council.streaming', 'streaming')}
                            </span>
                        )}
                        {status === 'error' && (
                            <span className="text-xs text-red-500 dark:text-red-400">
                                {t('council.error', 'error')}
                            </span>
                        )}
                    </div>
                </div>

                {status === 'error' && errorMessage ? (
                    <p className="text-xs text-red-500 dark:text-red-400">
                        {errorMessage}
                    </p>
                ) : !isExpanded ? (
                    <p className="text-xs text-charcoal/70 dark:text-white/50 leading-relaxed">
                        {preview}
                    </p>
                ) : null}
            </div>

            {/* Expanded full content */}
            {isExpanded && (
                <div className="px-3 pb-3 border-t border-grey-3 dark:border-white/10">
                    <div className="text-sm text-black dark:text-white/90 pt-2">
                        <Response>{content}</Response>
                    </div>
                </div>
            )}

            {/* Expand/collapse toggle */}
            {canExpand && status !== 'error' && (
                <button
                    type="button"
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="flex items-center gap-1 w-full px-3 py-2 text-xs text-charcoal/60 dark:text-white/40 hover:text-charcoal dark:hover:text-white/70 cursor-pointer border-t border-grey-3 dark:border-white/10 transition-colors"
                >
                    {isExpanded ? (
                        <>
                            <ChevronDown className="size-3" />
                            {t('common.showLess', 'Show less')}
                        </>
                    ) : (
                        <>
                            <ChevronRight className="size-3" />
                            {t('common.showMore', 'Show more')}
                        </>
                    )}
                </button>
            )}
        </div>
    )
}

interface CouncilResultDisplayProps {
    parts: ContentPart[]
}

export function CouncilResultDisplay({ parts }: CouncilResultDisplayProps) {
    const { t } = useTranslation()
    const [isCopied, setIsCopied] = useState(false)

    const memberParts = parts.filter(
        (p) => p.type === 'council_member_output'
    )
    const synthesisPart = parts.find((p) => p.type === 'council_synthesis')

    if (memberParts.length === 0) return null

    const isSynthesizing =
        synthesisPart &&
        !synthesisPart.content?.trim() &&
        !synthesisPart.error_message
    const hasSynthesisError = synthesisPart?.error_message

    const handleCopySynthesis = async () => {
        const text = synthesisPart?.content
        if (text) {
            await navigator.clipboard.writeText(text)
            setIsCopied(true)
            setTimeout(() => setIsCopied(false), 2000)
        }
    }

    return (
        <div className="w-full space-y-4 mb-6">
            {/* Model outputs - vertical stack */}
            <div>
                <div className="text-xs font-semibold text-charcoal dark:text-sky-blue mb-2 uppercase tracking-wide">
                    {t('council.modelResponses', 'Model Responses')}
                </div>
                <div className="flex flex-col gap-2">
                    {memberParts.map((part) => (
                        <ModelCard
                            key={part.model_id || part.id}
                            modelId={part.model_id || ''}
                            modelName={part.model_name || part.model_id || ''}
                            content={part.content || ''}
                            status={part.status || 'completed'}
                            errorMessage={part.error_message}
                        />
                    ))}
                </div>
            </div>

            {/* Synthesis section */}
            {synthesisPart && (
                <div className="border-t border-grey-3 dark:border-white/10 pt-4">
                    <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-semibold text-charcoal dark:text-sky-blue uppercase tracking-wide">
                            {t(
                                'council.synthesizedResponse',
                                'Synthesized Response'
                            )}
                        </span>
                        {isSynthesizing && (
                            <span className="flex items-center gap-1.5 text-xs text-sky-blue">
                                <span className="relative flex size-2">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-blue opacity-75" />
                                    <span className="relative inline-flex rounded-full size-2 bg-sky-blue" />
                                </span>
                                {t('council.synthesizing', 'synthesizing')}
                            </span>
                        )}
                    </div>
                    {hasSynthesisError ? (
                        <p className="text-sm text-red-500 dark:text-red-400">
                            {synthesisPart.error_message}
                        </p>
                    ) : (
                        <div className="group">
                            <Response>
                                {synthesisPart.content || ''}
                            </Response>
                        </div>
                    )}
                    {synthesisPart.content?.trim() && !hasSynthesisError && (
                        <div className="flex items-center gap-2 mt-3">
                            <Button
                                variant="ghost"
                                size="icon"
                                className="size-3 text-[10px] cursor-pointer"
                                onClick={handleCopySynthesis}
                            >
                                {isCopied ? (
                                    <Check className="size-3" />
                                ) : (
                                    <Copy className="size-3" />
                                )}
                            </Button>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
