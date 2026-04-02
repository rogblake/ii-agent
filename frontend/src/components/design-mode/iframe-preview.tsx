import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { DevicePreset } from './device-presets'
import { SavingOverlay } from './saving-overlay'
import type { SyncProgress } from './types'

interface IframePreviewProps {
    iframeRef: RefObject<HTMLIFrameElement | null>
    iframeSrc: string
    iframeSrcDoc?: string
    iframeSandbox: string
    iframeClassName?: string
    isEnabled: boolean
    isInteractMode?: boolean
    isSaving: boolean
    syncProgress: SyncProgress | null
    selectedDevice: DevicePreset
    deviceDimensions: { width: number; height: number }
}

export function IframePreview({
    iframeRef,
    iframeSrc,
    iframeSrcDoc,
    iframeSandbox,
    iframeClassName,
    isEnabled,
    isInteractMode,
    isSaving,
    syncProgress,
    selectedDevice,
    deviceDimensions
}: IframePreviewProps) {
    const { t } = useTranslation()

    const viewportRef = useRef<HTMLDivElement | null>(null)
    const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 })

    useEffect(() => {
        if (!viewportRef.current) return

        const el = viewportRef.current
        const update = () => {
            setViewportSize({ width: el.clientWidth, height: el.clientHeight })
        }
        update()

        if (typeof ResizeObserver === 'undefined') {
            window.addEventListener('resize', update)
            return () => window.removeEventListener('resize', update)
        }

        const observer = new ResizeObserver(update)
        observer.observe(el)
        return () => observer.disconnect()
    }, [])

    const isResponsive =
        selectedDevice.id === 'responsive' ||
        deviceDimensions.width === 0 ||
        deviceDimensions.height === 0

    const scale = useMemo(() => {
        if (isResponsive) return 1
        if (!viewportSize.width || !viewportSize.height) return 1
        if (!deviceDimensions.width || !deviceDimensions.height) return 1

        // Fit device into available viewport with padding.
        const padding = 24
        const availableWidth = Math.max(0, viewportSize.width - padding * 2)
        const availableHeight = Math.max(0, viewportSize.height - padding * 2)

        const scaleW = availableWidth / deviceDimensions.width
        const scaleH = availableHeight / deviceDimensions.height
        const next = Math.min(scaleW, scaleH)

        return Math.max(0.1, Math.min(1, next))
    }, [
        deviceDimensions.height,
        deviceDimensions.width,
        isResponsive,
        viewportSize.height,
        viewportSize.width
    ])

    return (
        <div className="flex-1 relative bg-neutral-200 dark:bg-neutral-800">
            <SavingOverlay isSaving={isSaving} syncProgress={syncProgress} />

            <div ref={viewportRef} className="absolute inset-0 overflow-hidden">
                <div
                    className={cn(
                        'flex items-start justify-center',
                        isResponsive
                            ? 'w-full h-full'
                            : 'inline-flex min-w-full'
                    )}
                >
                    <div
                        className={cn(
                            isResponsive
                                ? 'w-full h-full'
                                : 'bg-white shadow-2xl rounded-lg overflow-hidden flex-shrink-0'
                        )}
                        style={
                            isResponsive
                                ? undefined
                                : {
                                      width: deviceDimensions.width * scale,
                                      height: deviceDimensions.height * scale
                                  }
                        }
                    >
                        <iframe
                            ref={iframeRef}
                            src={iframeSrc}
                            srcDoc={iframeSrcDoc}
                            className={cn(
                                'border-0 bg-white',
                                isEnabled &&
                                    !isInteractMode &&
                                    'cursor-crosshair',
                                iframeClassName
                            )}
                            style={
                                isResponsive
                                    ? { width: '100%', height: '100%' }
                                    : {
                                          width: deviceDimensions.width,
                                          height: deviceDimensions.height,
                                          transform: `scale(${scale})`,
                                          transformOrigin: 'top left'
                                      }
                            }
                            sandbox={iframeSandbox}
                            title={t('common.preview')}
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}
