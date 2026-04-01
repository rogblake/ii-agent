/**
 * Design Panel Component
 *
 * Inspector panel for Design Mode (right sidebar).
 * Uses the Storybook-style inspector UI.
 */

import { useCallback, useMemo, useState } from 'react'
import { useParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import axiosInstance from '@/lib/axios'
import { toast } from 'sonner'
import { DesignInspectorPanel } from './design-inspector-panel'
import { useDesignModeContext } from './design-mode-context'
import { Textarea } from '@/components/ui/textarea'
import { Icon } from '@/components/ui/icon'

type StyleChangeGroup = {
    groupId: string
    groupLabel?: string
}

export function DesignPanel({ className }: { className?: string }) {
    const { sessionId } = useParams()
    const { t } = useTranslation()

    const {
        isEnabled,
        isReady,
        selectedElement,
        error,
        setStyleByDesignId,
        setTextByDesignId,
        setIconByDesignId,
        moveElementByDesignId,
        swapElementsByDesignId,
        requestDocumentSnapshot,
        setElementLoading
    } = useDesignModeContext()

    const [aiInput, setAiInput] = useState('')
    const [aiIsLoading, setAiIsLoading] = useState(false)

    const aiDisabledReason = useMemo(() => {
        if (!sessionId) return t('designMode.toasts.missingSessionId')
        if (!selectedElement) return t('designMode.toasts.selectElementFirst')
        return null
    }, [sessionId, selectedElement, t])

    const handleStyleChange = useCallback(
        (property: string, value: string, group?: StyleChangeGroup) => {
            if (!selectedElement) return
            setStyleByDesignId(selectedElement.designId, property, value, {
                xpath: selectedElement.xpath,
                slideNumber: selectedElement.slideNumber,
                groupId: group?.groupId,
                groupLabel: group?.groupLabel
            })
        },
        [selectedElement, setStyleByDesignId]
    )

    const handleTextChange = useCallback(
        (text: string) => {
            if (!selectedElement) return
            setTextByDesignId(selectedElement.designId, text, {
                xpath: selectedElement.xpath,
                slideNumber: selectedElement.slideNumber
            })
        },
        [selectedElement, setTextByDesignId]
    )

    const handleAiSubmit = useCallback(async () => {
        const userRequest = aiInput.trim()
        if (!userRequest) return
        if (!sessionId || !selectedElement) return
        if (aiIsLoading) return

        setAiIsLoading(true)
        setAiInput('')
        setElementLoading(selectedElement.designId, true)

        try {
            // Request document snapshot for full AI context
            const snapshot = await requestDocumentSnapshot({
                maxNodes: 1800,
                maxTextLen: 180,
                maxHtmlLen: 1200
            })

            if (!snapshot || !Array.isArray(snapshot.nodes)) {
                toast.error(t('designMode.toasts.snapshotFailed'))
                return
            }

            // Use the full AI iframe plan endpoint
            const response = await axiosInstance.post(
                '/v1/project/design/ai-iframe-plan',
                {
                    session_id: sessionId,
                    user_request: userRequest,
                    selected_element: {
                        designId: selectedElement.designId,
                        tagName: selectedElement.tagName,
                        className: selectedElement.className,
                        textContent: (selectedElement.textContent || '').slice(
                            0,
                            500
                        ),
                        computedStyles: selectedElement.computedStyles,
                        xpath: selectedElement.xpath
                    },
                    document_snapshot: snapshot
                }
            )

            const result = response?.data as
                | {
                    operations?: Array<Record<string, unknown>>
                    explanation?: string
                }
                | undefined

            const operations = Array.isArray(result?.operations)
                ? result?.operations
                : []
            const explanation =
                typeof result?.explanation === 'string'
                    ? result.explanation
                    : ''

            const groupId = `ai-${Date.now()}-${Math.random()
                .toString(16)
                .slice(2)}`
            const groupLabel =
                userRequest.length > 48
                    ? `${userRequest.slice(0, 48)}…`
                    : userRequest
            const aiSlideNumber = selectedElement?.slideNumber

            let appliedCount = 0
            for (const op of operations) {
                const opType = typeof op.op === 'string' ? op.op : null
                const designId =
                    typeof op.design_id === 'string' ? op.design_id : null
                if (!opType || !designId) continue

                if (opType === 'set_text') {
                    const text = typeof op.text === 'string' ? op.text : ''
                    setTextByDesignId(designId, text, {
                        xpath: selectedElement.xpath,
                        slideNumber: aiSlideNumber,
                        groupId,
                        groupLabel
                    })
                    appliedCount += 1
                    continue
                }

                if (opType === 'set_style') {
                    const property =
                        typeof op.property === 'string' ? op.property : null
                    const value = typeof op.value === 'string' ? op.value : ''
                    if (!property) continue
                    setStyleByDesignId(designId, property, value, {
                        xpath: selectedElement.xpath,
                        slideNumber: aiSlideNumber,
                        groupId,
                        groupLabel
                    })
                    appliedCount += 1
                    continue
                }

                if (opType === 'set_icon') {
                    const iconName =
                        typeof op.icon_name === 'string'
                            ? op.icon_name
                            : typeof op.iconName === 'string'
                                ? op.iconName
                                : ''
                    const svgInner =
                        typeof op.svg_inner === 'string'
                            ? op.svg_inner
                            : typeof op.svgInner === 'string'
                                ? op.svgInner
                                : ''
                    if (!iconName || !svgInner) continue
                    setIconByDesignId(designId, iconName, svgInner, {
                        xpath: selectedElement.xpath
                    })
                    appliedCount += 1
                    continue
                }

                if (opType === 'move') {
                    const anchor =
                        typeof op.anchor === 'string' ? op.anchor : null
                    if (!anchor) continue
                    moveElementByDesignId(designId, anchor)
                    appliedCount += 1
                    continue
                }

                if (opType === 'swap') {
                    const target =
                        typeof op.target_design_id === 'string'
                            ? op.target_design_id
                            : null
                    if (!target) continue
                    swapElementsByDesignId(designId, target)
                    appliedCount += 1
                    continue
                }
            }

            if (appliedCount === 0) {
                toast.message(
                    explanation || t('designMode.toasts.aiNoApplicableChanges')
                )
            } else if (explanation) {
                toast.message(explanation)
            }
        } catch (err) {
            console.error('[DesignPanel] AI apply error:', err)
            toast.error(t('designMode.toasts.aiApplyFailed'))
        } finally {
            setAiIsLoading(false)
            setElementLoading(selectedElement.designId, false)
        }
    }, [
        aiInput,
        aiIsLoading,
        selectedElement,
        sessionId,
        setStyleByDesignId,
        setTextByDesignId,
        setIconByDesignId,
        moveElementByDesignId,
        swapElementsByDesignId,
        requestDocumentSnapshot,
        setElementLoading,
        t
    ])

    return (
        <div
            data-design-mode-preserve-selection
            className={cn(
                'relative h-full w-full overflow-hidden bg-[#181e1c] text-white',
                className
            )}
        >
            {!isEnabled ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
                    <p className="text-sm font-semibold text-white/80">
                        {t('designMode.panel.inactive.title')}
                    </p>
                    <p className="text-xs text-white/50">
                        {t('designMode.panel.inactive.description')}
                    </p>
                </div>
            ) : error ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
                    <p className="text-sm font-semibold text-yellow-200">
                        {t('designMode.error.title')}
                    </p>
                    <p className="text-xs text-white/60">{error}</p>
                </div>
            ) : !isReady ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#a6ffff] border-t-transparent" />
                    <p className="text-sm text-white/70">
                        {t('designMode.panel.loading')}
                    </p>
                </div>
            ) : (
                <div className="relative flex h-full flex-col min-h-0">
                    <DesignInspectorPanel
                        className="flex-1 min-h-0 pb-[130px]"
                        sessionId={sessionId}
                        selectedElement={selectedElement}
                        onStyleChange={handleStyleChange}
                        onTextChange={handleTextChange}
                    />

                    <div
                        className={cn(
                            'absolute bottom-2 left-4 right-4 flex h-[116px] flex-col gap-3 rounded-[12px] border-2 border-[#E5E7EB] bg-[#121212]/56 px-4 py-[15px]',
                            !selectedElement && 'pointer-events-none opacity-40'
                        )}
                    >
                        <Textarea
                            value={aiInput}
                            onChange={(e) => setAiInput(e.target.value)}
                            placeholder={
                                aiDisabledReason
                                    ? aiDisabledReason
                                    : t('designMode.ai.placeholder')
                            }
                            className="flex-1 min-h-0 resize-none !border-0 !bg-transparent !p-0 !shadow-none !rounded-none text-[14px] leading-[19px] text-white placeholder:text-white/[0.48] focus-visible:!ring-0 focus-visible:!border-0 focus-visible:!outline-none"
                            disabled={Boolean(aiDisabledReason) || aiIsLoading}
                            onKeyDown={(e) => {
                                if (
                                    e.key === 'Enter' &&
                                    !e.shiftKey &&
                                    !e.nativeEvent.isComposing
                                ) {
                                    e.preventDefault()
                                    void handleAiSubmit()
                                }
                            }}
                        />

                        <div className="flex items-center justify-end">
                            <button
                                type="button"
                                className={cn(
                                    'group flex h-7 w-7 items-center justify-center rounded-full bg-white/40',
                                    'transition-all duration-200',
                                    'hover:bg-white/50 hover:scale-110 hover:shadow-[0px_6px_18px_rgba(0,0,0,0.18)] active:scale-95',
                                    'disabled:opacity-50'
                                )}
                                disabled={
                                    aiIsLoading ||
                                    !aiInput.trim() ||
                                    Boolean(aiDisabledReason)
                                }
                                onClick={() => void handleAiSubmit()}
                                title={aiDisabledReason ?? t('common.apply')}
                            >
                                {aiIsLoading ? (
                                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                                ) : (
                                    <Icon
                                        name="arrow-up-3"
                                        className="size-[18px] text-white transition-transform duration-200 group-hover:-translate-y-1"
                                    />
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
