import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { mediaToolsService } from '@/services/media-tools.service'
import { type MiniTool } from '@/constants/media-tools'
import {
    removeFromCurrentMessageFileIds,
    selectChatMediaPreference,
    setChatMediaPreference,
    useAppDispatch,
    useAppSelector
} from '@/state'
import type { AdvancedModeSettings } from '@/typings/chat'
import { Button } from '../../ui/button'
import { Icon } from '../../ui/icon'
import MiniToolBoardOverlay from './mini-tool-board-overlay'
import { useTranslation } from 'react-i18next'
import { AdvancedModeController } from './advanced-mode-controller'

type Props = {
    disabled?: boolean
    sessionId?: string
    modelName?: string
    provider?: string
    clearSignal?: number
    onSelect: (tool: MiniTool) => void
    onClear: () => void
    advancedModeSettings?: AdvancedModeSettings | null
    onAdvancedModeSettingsChange?: (
        settings: AdvancedModeSettings | null
    ) => void
    previewPortalTarget?: HTMLElement | null
}

const ChatMiniTools = ({
    disabled,
    sessionId,
    modelName,
    provider,
    clearSignal,
    onSelect,
    onClear,
    advancedModeSettings,
    onAdvancedModeSettingsChange,
    previewPortalTarget
}: Props) => {
    const { t } = useTranslation()
    const toolNameMap = t('media.miniTools.toolNames', {
        returnObjects: true
    }) as Record<string, string>
    const dispatch = useAppDispatch()
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)

    const [tools, setTools] = useState<MiniTool[]>([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [open, setOpen] = useState(false)
    const [boardOpen, setBoardOpen] = useState(false)
    const [boardDismissed, setBoardDismissed] = useState(false)
    const [isAdvancedModeActive, setIsAdvancedModeActive] = useState(
        () => advancedModeSettings?.enabled ?? false
    )
    const popoverRef = useRef<HTMLDivElement | null>(null)
    const [localSelectedTool, setLocalSelectedTool] = useState<{
        id: string
        name: string
    } | null>(null)
    // Track if user just selected a tool (vs restored from session state)
    const userJustSelectedToolRef = useRef(false)

    // Allow parent to trigger a clear without relying on global state
    useEffect(() => {
        if (clearSignal === undefined) return

        setLocalSelectedTool(null)
        setBoardOpen(false)
        setBoardDismissed(false)
        userJustSelectedToolRef.current = false
    }, [clearSignal])

    const effectiveSelectedTool = localSelectedTool

    // When mini tool preference is cleared (e.g., after a response), reset local selection/board
    useEffect(() => {
        if (!chatMediaPreference.mini_tools) {
            setLocalSelectedTool(null)
            setBoardOpen(false)
            setBoardDismissed(false)
            userJustSelectedToolRef.current = false
        }
    }, [chatMediaPreference.mini_tools])

    // Sync advanced mode active state from settings
    useEffect(() => {
        setIsAdvancedModeActive(advancedModeSettings?.enabled ?? false)
    }, [advancedModeSettings?.enabled])

    // Handle advanced mode settings change from controller
    const handleAdvancedModeSettingsChange = useCallback(
        (settings: AdvancedModeSettings | null) => {
            setIsAdvancedModeActive(settings?.enabled ?? false)
            onAdvancedModeSettingsChange?.(settings)
        },
        [onAdvancedModeSettingsChange]
    )

    useEffect(() => {
        let mounted = true
        setLoading(true)
        mediaToolsService
            .listMediaTools()
            .then((res) => {
                if (mounted) setTools(res)
            })
            .catch((err) => {
                console.error('Failed to load mini tools', err)
                if (mounted) setError(t('media.miniTools.loadError') as string)
            })
            .finally(() => {
                if (mounted) setLoading(false)
            })
        return () => {
            mounted = false
        }
    }, [t])

    const renderPreview = (tool: MiniTool, toolLabel: string) => {
        if (tool.preview) {
            return (
                <img
                    src={tool.preview}
                    alt={toolLabel}
                    className="h-full w-full rounded-[12px] object-cover"
                />
            )
        }

        return (
            <div className="flex h-full w-full items-center justify-center">
                <div className="flex w-[90%] items-center justify-between gap-3">
                    <div className="relative h-[85px] w-[72px] rounded-lg bg-gradient-to-br from-[#dcdfe5] via-white to-[#c7ccd4] dark:from-[#1f2b34] dark:via-[#0f1f26] dark:to-[#24323c]">
                        <span className="absolute inset-x-0 bottom-2 text-center text-[10px] font-semibold text-[#212121] dark:text-white">
                            {t('media.miniTools.before')}
                        </span>
                    </div>
                    <span className="text-lg text-[#6b7280] dark:text-grey-1">
                        →
                    </span>
                    <div className="relative h-[85px] w-[72px] rounded-lg bg-gradient-to-br from-[#dfeafc] via-white to-[#bad8ff] dark:from-[#1d2f3d] dark:via-[#0f1f26] dark:to-[#1f3d52]">
                        <span className="absolute inset-x-0 bottom-2 text-center text-[10px] font-semibold text-[#212121] dark:text-white">
                            {t('media.miniTools.after')}
                        </span>
                    </div>
                </div>
            </div>
        )
    }

    const selectedName = useMemo(() => {
        if (!effectiveSelectedTool) return undefined
        return (
            toolNameMap?.[effectiveSelectedTool.name] ??
            effectiveSelectedTool.name
        )
    }, [effectiveSelectedTool, toolNameMap])

    const handleSelect = (tool: MiniTool) => {
        userJustSelectedToolRef.current = true
        onSelect(tool)
        setLocalSelectedTool({ id: tool.id, name: tool.name })
        setOpen(false)
    }

    const selectedToolDetail = useMemo(
        () => tools.find((tool) => tool.id === effectiveSelectedTool?.id),
        [tools, effectiveSelectedTool]
    )

    useEffect(() => {
        if (!open) return

        const handleClickOutside = (event: MouseEvent) => {
            if (
                popoverRef.current &&
                !popoverRef.current.contains(event.target as Node)
            ) {
                setOpen(false)
            }
        }

        document.addEventListener('mousedown', handleClickOutside)

        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
        }
    }, [open])

    useEffect(() => {
        if (effectiveSelectedTool) {
            // Only open board if user just selected a tool (not restored from session)
            // and it hasn't been dismissed by user action
            if (userJustSelectedToolRef.current && !boardDismissed) {
                setBoardOpen(true)
                userJustSelectedToolRef.current = false
            }
        } else {
            // Reset local state when tool is cleared
            setBoardOpen(false)
            setBoardDismissed(false)
            setLocalSelectedTool(null)
            userJustSelectedToolRef.current = false
        }
    }, [effectiveSelectedTool, boardDismissed])

    const boardOverlay =
        effectiveSelectedTool && boardOpen ? (
            <MiniToolBoardOverlay
                open={boardOpen}
                selectedTool={
                    effectiveSelectedTool
                        ? {
                              id: effectiveSelectedTool.id,
                              name: effectiveSelectedTool.name
                          }
                        : null
                }
                toolDetail={selectedToolDetail}
                sessionId={sessionId}
                onClose={() => {
                    setBoardOpen(false)
                    setBoardDismissed(true)
                }}
                onClear={() => {
                    setLocalSelectedTool(null)
                    onClear()
                }}
            />
        ) : null

    return (
        <div className="relative w-full">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    {/* Advanced Mode Controller - hidden when mini tool is selected */}
                    <AdvancedModeController
                        disabled={disabled}
                        sessionId={sessionId}
                        modelName={modelName}
                        provider={provider}
                        advancedModeSettings={advancedModeSettings}
                        onAdvancedModeSettingsChange={
                            handleAdvancedModeSettingsChange
                        }
                        hiddenByMiniTool={!!effectiveSelectedTool}
                        showPreviewPosition="inline"
                        previewPortalTarget={previewPortalTarget}
                    />

                    {effectiveSelectedTool ? (
                        <div className="flex items-center gap-2">
                            {/* Tool chip */}
                            <div
                                className="inline-flex h-8 items-center gap-2 rounded-full px-3 shadow-sm cursor-pointer transition-all duration-200 hover:shadow-md bg-firefly dark:bg-sky-blue-2"
                                onClick={() => {
                                    setBoardDismissed(false)
                                    setBoardOpen(true)
                                }}
                            >
                                <Icon
                                    name="ai-magic"
                                    className="size-4 flex-shrink-0 fill-sky-blue dark:fill-black"
                                />
                                <span
                                    className="min-w-0 text-xs font-semibold text-sky-blue dark:text-black truncate max-w-[160px]"
                                    title={selectedName}
                                >
                                    {selectedName}
                                </span>
                                <Button
                                    size="icon"
                                    variant="ghost"
                                    className="ml-1 h-5 w-5 flex-shrink-0 rounded-full hover:bg-black/10 dark:hover:bg-white/10"
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        // Remove reference files from currentMessageFileIds (for preview cleanup)
                                        const refFileIds =
                                            chatMediaPreference.mini_tools
                                                ?.reference_file_ids ?? []
                                        if (refFileIds.length > 0) {
                                            dispatch(
                                                removeFromCurrentMessageFileIds(
                                                    refFileIds
                                                )
                                            )
                                        }
                                        // Clear mini_tools and reference_file_ids from chatMediaPreference
                                        dispatch(
                                            setChatMediaPreference({
                                                ...chatMediaPreference,
                                                mini_tools: undefined
                                            })
                                        )
                                        setLocalSelectedTool(null)
                                        onClear()
                                        setBoardOpen(false)
                                    }}
                                    title={t('media.miniTools.clear')}
                                >
                                    <Icon
                                        name="close"
                                        className="size-3 fill-white dark:fill-black"
                                    />
                                </Button>
                            </div>
                        </div>
                    ) : (
                        !isAdvancedModeActive && (
                            <Button
                                variant="secondary"
                                size="sm"
                                className="rounded-full text-xs h-8 px-3 text-sky-blue-2 shadow-sm bg-firefly dark:bg-sky-blue-2/10"
                                disabled={disabled}
                                onClick={() => setOpen((prev) => !prev)}
                            >
                                <Icon
                                    name="plus"
                                    className="size-4 fill-sky-blue-2"
                                />
                                {t('media.miniTools.buttonLabel')}
                            </Button>
                        )
                    )}
                </div>
            </div>

            {open && (
                <div className="absolute left-0 right-0 bottom-full mb-3 z-30">
                    <div
                        ref={popoverRef}
                        className="mx-auto w-full md:max-w-[620px] rounded-2xl bg-white px-3 py-3 shadow-btn backdrop-blur-md"
                    >
                        {loading && (
                            <div className="text-sm text-[#6b7280] dark:text-grey-1">
                                {t('media.miniTools.loading')}
                            </div>
                        )}
                        {error && (
                            <div className="text-sm text-red-500">{error}</div>
                        )}

                        {!loading && !error && (
                            <div className="max-h-[calc(100vh-250px)] md:max-h-[540px] overflow-y-auto pr-1">
                                <div className="grid grid-cols-2 md:grid-cols-3 gap-y-3">
                                    {tools.map((tool) => (
                                        <button
                                            key={tool.id}
                                            onClick={() => handleSelect(tool)}
                                            className="group flex w-full flex-col items-center text-center cursor-pointer"
                                            disabled={disabled}
                                        >
                                            <div className="relative aspect-[170/126] w-full overflow-hidden rounded-[12px] bg-white transition hover:-translate-y-0.5">
                                                {renderPreview(
                                                    tool,
                                                    toolNameMap?.[tool.name] ??
                                                        tool.name
                                                )}
                                            </div>
                                            <div
                                                className="text-sm font-medium text-black"
                                                title={
                                                    toolNameMap?.[tool.name] ??
                                                    tool.name
                                                }
                                            >
                                                {toolNameMap?.[tool.name] ??
                                                    tool.name}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {boardOverlay}
        </div>
    )
}

export default ChatMiniTools
