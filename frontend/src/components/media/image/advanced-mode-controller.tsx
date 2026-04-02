import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { chatService } from '@/services/chat.service'
import {
    selectChatMediaPreference,
    setChatMediaPreference,
    useAppDispatch,
    useAppSelector
} from '@/state'
import type {
    AdvancedModeReference,
    AdvancedModeSettings,
    MediaReference
} from '@/typings/chat'
import { Button } from '../../ui/button'
import { AdvancedModeModal, type AdvancedModeData } from './advanced-mode-modal'
import { AdvancedModePreview } from './advanced-mode-preview'
import { useIsMobile } from '@/hooks/use-mobile'

export type AdvancedModeControllerProps = {
    disabled?: boolean
    sessionId?: string
    modelName?: string
    provider?: string
    advancedModeSettings?: AdvancedModeSettings | null
    onAdvancedModeSettingsChange?: (
        settings: AdvancedModeSettings | null
    ) => void
    /** Hide toggle button when a mini tool is selected */
    hiddenByMiniTool?: boolean
    /** Custom class for the toggle button */
    toggleButtonClassName?: string
    /** Custom class for the preview component */
    previewClassName?: string
    /** Show preview in a specific position */
    showPreviewPosition?: 'inline' | 'fixed'
    /** When provided, render inline preview via portal into this element */
    previewPortalTarget?: HTMLElement | null
}

export const AdvancedModeController = ({
    disabled,
    sessionId,
    modelName,
    provider,
    advancedModeSettings,
    onAdvancedModeSettingsChange,
    hiddenByMiniTool = false,
    toggleButtonClassName = '',
    previewClassName = '',
    showPreviewPosition = 'fixed',
    previewPortalTarget
}: AdvancedModeControllerProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)
    const chatMediaPreferenceRef = useRef(chatMediaPreference)
    const isMobile = useIsMobile()

    const [advancedModeOpen, setAdvancedModeOpen] = useState(false)
    const [advancedModeData, setAdvancedModeData] =
        useState<AdvancedModeData | null>(null)
    const [isAdvancedModeActive, setIsAdvancedModeActive] = useState(false)
    const [updatingAdvancedMode, setUpdatingAdvancedMode] = useState(false)
    const lastAppliedKeyRef = useRef<string | null>(null)

    // Keep ref in sync early so other effects read the latest preference
    useEffect(() => {
        chatMediaPreferenceRef.current = chatMediaPreference
    }, [chatMediaPreference])

    const mapSettingsToData = useCallback(
        (settings?: AdvancedModeSettings | null): AdvancedModeData => {
            const base: AdvancedModeData = {
                subject: { images: [], prompt: '' },
                scene: { images: [], prompt: '' },
                style: { images: [], prompt: '' }
            }

            if (!settings?.references?.length) {
                return base
            }

            settings.references.forEach((ref) => {
                const key = ref.type as keyof AdvancedModeData
                if (!key || !(key in base)) return
                base[key].images.push({
                    preview: ref.file_url || '',
                    fileId: ref.file_id
                })
            })

            return base
        },
        []
    )

    const extractReferences = useCallback(
        (data: AdvancedModeData | null): MediaReference[] => {
            if (!data) return []
            const refs: MediaReference[] = []
            ;(
                ['subject', 'scene', 'style'] as Array<keyof AdvancedModeData>
            ).forEach((key) => {
                data[key].images.forEach((img) => {
                    if (img.fileId) {
                        refs.push({
                            file_id: img.fileId,
                            type: key
                        })
                    }
                })
            })

            const deduped = new Map<string, MediaReference>()
            refs.forEach((ref) => {
                const key = `${ref.type ?? ''}-${ref.file_id}`
                if (!deduped.has(key)) {
                    deduped.set(key, ref)
                }
            })

            return Array.from(deduped.values())
        },
        []
    )

    const buildSettingsFromData = useCallback(
        (
            data: AdvancedModeData | null,
            enabled = true
        ): AdvancedModeSettings => {
            if (!enabled) {
                return { enabled: false, references: [] }
            }

            if (!data) {
                return { enabled: true, references: [] }
            }

            const refs: AdvancedModeReference[] = []
            ;(
                ['subject', 'scene', 'style'] as Array<keyof AdvancedModeData>
            ).forEach((key) => {
                data[key].images.forEach((img) => {
                    if (!img.fileId) return
                    refs.push({
                        file_id: img.fileId,
                        type: key,
                        file_url: img.fileUrl || img.preview || undefined
                    })
                })
            })

            return { enabled: true, references: refs }
        },
        []
    )

    const buildSettingsKey = useCallback(
        (settings: AdvancedModeSettings | null): string => {
            if (!settings) return 'null'
            const refs = settings.references?.map(
                (ref) =>
                    `${ref.type ?? ''}:${ref.file_id ?? ''}:${ref.file_url ?? ''}`
            )
            return `${settings.enabled ? '1' : '0'}|${refs?.join('|') ?? ''}`
        },
        []
    )

    const applyAdvancedSettings = useCallback(
        (settings: AdvancedModeSettings | null, notifyParent = false) => {
            if (!notifyParent) {
                const nextKey = buildSettingsKey(settings)
                if (nextKey === lastAppliedKeyRef.current) {
                    return
                }
                lastAppliedKeyRef.current = nextKey
            }

            if (notifyParent && onAdvancedModeSettingsChange) {
                onAdvancedModeSettingsChange(settings)
            }

            setIsAdvancedModeActive(Boolean(settings?.enabled))
            const currentPreference = chatMediaPreferenceRef.current

            if (settings?.enabled) {
                setAdvancedModeData(mapSettingsToData(settings))
                dispatch(
                    setChatMediaPreference({
                        ...currentPreference,
                        enabled: true,
                        type: 'image',
                        mini_tools: undefined,
                        references: settings.references.map((ref) => ({
                            file_id: ref.file_id,
                            type: ref.type
                        })),
                        advanced_mode: true
                    })
                )
            } else {
                setAdvancedModeData(null)
                setAdvancedModeOpen(false)
                dispatch(
                    setChatMediaPreference({
                        ...currentPreference,
                        references: undefined,
                        advanced_mode: false
                    })
                )
            }
        },
        [
            buildSettingsKey,
            dispatch,
            mapSettingsToData,
            onAdvancedModeSettingsChange
        ]
    )

    useEffect(() => {
        if (advancedModeSettings) {
            applyAdvancedSettings(advancedModeSettings)
        } else {
            setAdvancedModeData(null)
            setIsAdvancedModeActive(false)
        }
    }, [advancedModeSettings, applyAdvancedSettings])

    // Hide advanced mode UI when mini tool is selected
    useEffect(() => {
        if (hiddenByMiniTool) {
            setIsAdvancedModeActive(false)
        }
    }, [hiddenByMiniTool])

    const handleAdvancedModeToggle = async () => {
        if (disabled || updatingAdvancedMode) return

        setUpdatingAdvancedMode(true)
        try {
            if (!sessionId) {
                if (isAdvancedModeActive) {
                    const settings = buildSettingsFromData(null, false)
                    applyAdvancedSettings(settings, true)
                } else {
                    const settings = buildSettingsFromData(
                        advancedModeData ?? null,
                        true
                    )
                    applyAdvancedSettings(settings, true)
                    setAdvancedModeOpen(true)
                }
                return
            }
            if (isAdvancedModeActive) {
                const response = await chatService.updateAdvancedModeSettings(
                    sessionId,
                    { enabled: false, references: [] }
                )
                applyAdvancedSettings(response, true)
            } else {
                const response = await chatService.updateAdvancedModeSettings(
                    sessionId,
                    {
                        enabled: true,
                        references: extractReferences(advancedModeData ?? null)
                    }
                )
                applyAdvancedSettings(response, true)
                setAdvancedModeOpen(true)
            }
        } catch (error) {
            console.error('Failed to toggle advanced mode', error)
            toast.error(
                isAdvancedModeActive
                    ? t('media.advancedMode.errors.disableFailed')
                    : t('media.advancedMode.errors.enableFailed')
            )
        } finally {
            setUpdatingAdvancedMode(false)
        }
    }

    const handleAdvancedModeSave = async (data: AdvancedModeData) => {
        if (!sessionId) {
            const settings = buildSettingsFromData(data, true)
            applyAdvancedSettings(settings, true)
            setAdvancedModeOpen(false)
            toast.success(t('media.advancedMode.success.saved'))
            return
        }

        setUpdatingAdvancedMode(true)
        try {
            const response = await chatService.updateAdvancedModeSettings(
                sessionId,
                {
                    enabled: true,
                    references: extractReferences(data)
                }
            )
            applyAdvancedSettings(response, true)
            setAdvancedModeOpen(false)
            toast.success(t('media.advancedMode.success.saved'))
        } catch (error) {
            console.error('Failed to save advanced mode references', error)
            toast.error(t('media.advancedMode.errors.saveFailed'))
            throw error instanceof Error
                ? error
                : new Error(t('media.advancedMode.errors.saveFailed'))
        } finally {
            setUpdatingAdvancedMode(false)
        }
    }

    const handleAdvancedModeClose = () => {
        setAdvancedModeOpen(false)
    }

    const showInlinePreview =
        showPreviewPosition === 'inline' ||
        (showPreviewPosition === 'fixed' && isMobile)
    const showFixedPreview = showPreviewPosition === 'fixed' && !isMobile

    return (
        <>
            {/* Toggle Button */}
            {!hiddenByMiniTool && (
                <Button
                    variant="outline"
                    size="sm"
                    className={`rounded-full text-xs h-8 px-3 transition-colors ${
                        isAdvancedModeActive
                            ? 'border-sky-blue !bg-sky-blue text-black'
                            : 'bg-firefly dark:bg-sky-blue-2/10 text-sky-blue-2 hover:bg-sky-blue-2 hover:text-black hover:border-sky-blue-2'
                    } ${toggleButtonClassName}`}
                    disabled={disabled || updatingAdvancedMode}
                    onClick={handleAdvancedModeToggle}
                >
                    {t('media.advancedMode.toggleLabel')}
                </Button>
            )}

            {/* Inline Preview (for mobile or when specified) — hidden when modal is open */}
            {!hiddenByMiniTool &&
                isAdvancedModeActive &&
                !advancedModeOpen &&
                showInlinePreview &&
                (isMobile && previewPortalTarget
                    ? createPortal(
                          <AdvancedModePreview
                              data={advancedModeData}
                              onEdit={() => setAdvancedModeOpen(true)}
                              className={previewClassName}
                              usePortal
                          />,
                          previewPortalTarget
                      )
                    : (
                          <AdvancedModePreview
                              data={advancedModeData}
                              onEdit={() => setAdvancedModeOpen(true)}
                              className={previewClassName}
                          />
                      ))}

            {/* Modal */}
            <AdvancedModeModal
                open={advancedModeOpen}
                sessionId={sessionId}
                modelName={modelName}
                provider={provider}
                initialData={advancedModeData}
                onClose={handleAdvancedModeClose}
                onSave={handleAdvancedModeSave}
            />

            {/* Fixed Preview (for desktop) — hidden when modal is open */}
            {!hiddenByMiniTool && isAdvancedModeActive && !advancedModeOpen && showFixedPreview && (
                <AdvancedModePreview
                    data={advancedModeData}
                    onEdit={() => setAdvancedModeOpen(true)}
                    className={previewClassName}
                />
            )}
        </>
    )
}

export default AdvancedModeController
