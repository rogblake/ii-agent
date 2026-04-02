/**
 * Device Toolbar Component
 *
 * Provides device selection, rotation, zoom controls, and action buttons for design mode.
 */

import { useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
    Monitor,
    Smartphone,
    Tablet,
    ChevronDown,
    RotateCcw,
    Minus,
    Plus,
    Undo2,
    Loader2,
    Trash2,
    MousePointer2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '@/components/ui/select'
import {
    DEVICE_PRESETS,
    ZOOM_PRESETS,
    type DevicePreset
} from './device-presets'
import type { DesignChange, SyncProgress } from './types'

interface DeviceToolbarProps {
    selectedDevice: DevicePreset
    onDeviceChange: (device: DevicePreset) => void
    isRotated: boolean
    onRotate: () => void
    zoom: number
    onZoomChange: (zoom: number) => void
    isEnabled: boolean
    pendingChanges: DesignChange[]
    isSaving: boolean
    syncProgress: SyncProgress | null
    onOpenChangesPanel: () => void
    onSaveClick: () => void
    isMultiSelectMode?: boolean
    multiSelectedCount?: number
    onToggleMultiSelect?: () => void
    onDeleteSelected?: () => void
}

function DeviceIcon({
    type,
    className
}: {
    type: DevicePreset['type']
    className?: string
}) {
    switch (type) {
        case 'mobile':
            return <Smartphone className={className} />
        case 'tablet':
            return <Tablet className={className} />
        default:
            return <Monitor className={className} />
    }
}

export function DeviceToolbar({
    selectedDevice,
    onDeviceChange,
    isRotated,
    onRotate,
    zoom,
    onZoomChange,
    isEnabled,
    pendingChanges,
    isSaving,
    syncProgress,
    onOpenChangesPanel,
    onSaveClick,
    isMultiSelectMode = false,
    multiSelectedCount = 0,
    onToggleMultiSelect,
    onDeleteSelected
}: DeviceToolbarProps) {
    const { t } = useTranslation()

    const selectedDeviceLabel =
        selectedDevice.id === 'responsive'
            ? t('designMode.toolbar.responsive')
            : selectedDevice.name

    // Calculate actual device dimensions (considering rotation)
    const deviceDimensions = useMemo(() => {
        if (selectedDevice.id === 'responsive') {
            return { width: 0, height: 0 }
        }
        return isRotated
            ? { width: selectedDevice.height, height: selectedDevice.width }
            : { width: selectedDevice.width, height: selectedDevice.height }
    }, [selectedDevice, isRotated])

    // Group devices by type for dropdown
    const deviceGroups = useMemo(
        () => ({
            desktop: DEVICE_PRESETS.filter((d) => d.type === 'desktop'),
            tablet: DEVICE_PRESETS.filter((d) => d.type === 'tablet'),
            mobile: DEVICE_PRESETS.filter((d) => d.type === 'mobile')
        }),
        []
    )

    // Check if current device supports rotation (tablets and phones)
    const canRotate =
        selectedDevice.type !== 'desktop' && selectedDevice.id !== 'responsive'

    const handleZoomIn = useCallback(() => {
        if (zoom < 200) {
            onZoomChange(Math.min(zoom + 1, 200))
        }
    }, [zoom, onZoomChange])

    const handleZoomOut = useCallback(() => {
        if (zoom > 25) {
            onZoomChange(Math.max(zoom - 1, 25))
        }
    }, [zoom, onZoomChange])

    const handleDeviceSelect = useCallback(
        (device: DevicePreset) => {
            onDeviceChange(device)
        },
        [onDeviceChange]
    )

    return (
        <div
            data-design-mode-preserve-selection
            className="flex-shrink-0 flex items-center gap-2 px-3 py-2 bg-[#181e1c] border-b border-white/10 text-white"
        >
            {/* Device Selector Dropdown */}
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="outline"
                        size="sm"
                        className={cn(
                            'h-9 gap-2 text-xs font-medium min-w-[180px] justify-between rounded-xl',
                            'border-white/10 bg-[#202927] text-white/80',
                            'hover:bg-[#24302e] hover:text-white hover:border-white/30'
                        )}
                    >
                        <div className="flex items-center gap-2">
                            <DeviceIcon
                                type={selectedDevice.type}
                                className="h-4 w-4"
                            />
                            <span className="truncate">
                                {selectedDeviceLabel}
                            </span>
                        </div>
                        <ChevronDown className="h-3 w-3 opacity-50 flex-shrink-0" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                    align="start"
                    className="w-64 max-h-[400px] overflow-y-auto bg-[#202927] border-white/10 text-white"
                    data-design-mode-preserve-selection
                >
                    {/* Responsive */}
                    <DropdownMenuItem
                        onClick={() => handleDeviceSelect(DEVICE_PRESETS[0])}
                        className={cn(
                            'gap-2 focus:bg-[#24302e] focus:text-white',
                            selectedDevice.id === 'responsive' &&
                                'bg-[#24302e] text-white'
                        )}
                    >
                        <Monitor className="h-4 w-4" />
                        <span>{t('designMode.toolbar.responsive')}</span>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />

                    {/* Desktop / Laptop */}
                    <div className="px-2 py-1.5 text-xs font-semibold text-white/50">
                        {t('designMode.toolbar.deviceGroups.desktop')}
                    </div>
                    {deviceGroups.desktop.slice(1).map((device) => (
                        <DropdownMenuItem
                            key={device.id}
                            onClick={() => handleDeviceSelect(device)}
                            className={cn(
                                'gap-2 focus:bg-[#24302e] focus:text-white',
                                selectedDevice.id === device.id &&
                                    'bg-[#24302e] text-white'
                            )}
                        >
                            <Monitor className="h-4 w-4" />
                            <span className="flex-1">{device.name}</span>
                            <span className="text-xs text-white/40">
                                {device.width}×{device.height}
                            </span>
                        </DropdownMenuItem>
                    ))}
                    <DropdownMenuSeparator />

                    {/* Tablet */}
                    <div className="px-2 py-1.5 text-xs font-semibold text-white/50">
                        {t('designMode.toolbar.deviceGroups.tablet')}
                    </div>
                    {deviceGroups.tablet.map((device) => (
                        <DropdownMenuItem
                            key={device.id}
                            onClick={() => handleDeviceSelect(device)}
                            className={cn(
                                'gap-2 focus:bg-[#24302e] focus:text-white',
                                selectedDevice.id === device.id &&
                                    'bg-[#24302e] text-white'
                            )}
                        >
                            <Tablet className="h-4 w-4" />
                            <span className="flex-1">{device.name}</span>
                            <span className="text-xs text-white/40">
                                {device.width}×{device.height}
                            </span>
                        </DropdownMenuItem>
                    ))}
                    <DropdownMenuSeparator />

                    {/* Mobile */}
                    <div className="px-2 py-1.5 text-xs font-semibold text-white/50">
                        {t('designMode.toolbar.deviceGroups.mobile')}
                    </div>
                    {deviceGroups.mobile.map((device) => (
                        <DropdownMenuItem
                            key={device.id}
                            onClick={() => handleDeviceSelect(device)}
                            className={cn(
                                'gap-2 focus:bg-[#24302e] focus:text-white',
                                selectedDevice.id === device.id &&
                                    'bg-[#24302e] text-white'
                            )}
                        >
                            <Smartphone className="h-4 w-4" />
                            <span className="flex-1">{device.name}</span>
                            <span className="text-xs text-white/40">
                                {device.width}×{device.height}
                            </span>
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>

            {/* Dimensions Display */}
            {selectedDevice.id !== 'responsive' && (
                <span className="text-xs text-white/50 tabular-nums">
                    {deviceDimensions.width} × {deviceDimensions.height}
                </span>
            )}

            {/* Rotate Button */}
            <Button
                variant="outline"
                size="sm"
                className={cn(
                    'h-9 w-9 p-0 rounded-xl',
                    'border-white/10 bg-[#202927] text-white/70',
                    'hover:bg-[#24302e] hover:text-white hover:border-white/30'
                )}
                onClick={onRotate}
                disabled={!canRotate}
                title={
                    canRotate
                        ? t('designMode.toolbar.rotateDevice')
                        : t('designMode.toolbar.rotationNotAvailable')
                }
            >
                <RotateCcw
                    className={cn('h-4 w-4', isRotated && 'text-[#a6ffff]')}
                />
            </Button>

            {/* Separator */}
            <div className="w-px h-5 bg-white/10" />

            {/* Zoom Controls */}
            <div className="flex items-center gap-1">
                <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                        'h-9 w-9 p-0 rounded-xl',
                        'border-white/10 bg-[#202927] text-white/70',
                        'hover:bg-[#24302e] hover:text-white hover:border-white/30'
                    )}
                    onClick={handleZoomOut}
                    disabled={zoom <= 25}
                    title={t('designMode.toolbar.zoomOut')}
                >
                    <Minus className="h-4 w-4" />
                </Button>

                <Select
                    value={zoom.toString()}
                    onValueChange={(value) => onZoomChange(parseInt(value))}
                >
                    <SelectTrigger className="!h-9 min-w-[80px] w-auto text-xs rounded-xl border border-white/10 bg-[#202927] text-white/80 focus:ring-1 focus:ring-[#a6ffff]/40">
                        <SelectValue>{zoom}%</SelectValue>
                    </SelectTrigger>
                    <SelectContent
                        className="bg-[#202927] border-white/10 text-white"
                        data-design-mode-preserve-selection
                    >
                        {ZOOM_PRESETS.map((z) => (
                            <SelectItem key={z} value={z.toString()}>
                                {z}%
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>

                <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                        'h-9 w-9 p-0 rounded-xl',
                        'border-white/10 bg-[#202927] text-white/70',
                        'hover:bg-[#24302e] hover:text-white hover:border-white/30'
                    )}
                    onClick={handleZoomIn}
                    disabled={zoom >= 200}
                    title={t('designMode.toolbar.zoomIn')}
                >
                    <Plus className="h-4 w-4" />
                </Button>
            </div>
            {/* Multi-Select Delete Controls */}
            {isEnabled && onToggleMultiSelect && (
                <>
                    <div className="w-px h-5 bg-white/10" />
                    <Button
                        variant="outline"
                        size="sm"
                        className={cn(
                            'h-9 gap-2 rounded-xl',
                            'border-white/10 bg-[#202927] text-white/80',
                            'hover:bg-[#24302e] hover:text-white hover:border-white/30',
                            isMultiSelectMode &&
                                'border-red-500/50 bg-red-500/10 text-white'
                        )}
                        onClick={onToggleMultiSelect}
                        title={
                            isMultiSelectMode
                                ? t('designMode.toolbar.exitMultiSelect')
                                : t('designMode.toolbar.multiSelectDelete')
                        }
                    >
                        <MousePointer2
                            className={cn(
                                'h-4 w-4',
                                isMultiSelectMode && 'text-red-500'
                            )}
                        />
                        <span className="text-xs font-semibold">
                            {isMultiSelectMode
                                ? t('designMode.toolbar.selecting')
                                : t('designMode.toolbar.delete')}
                        </span>
                        {isMultiSelectMode && multiSelectedCount > 0 && (
                            <span className="px-1.5 py-0.5 bg-red-500 text-white rounded-full text-[10px] font-bold min-w-[18px] text-center">
                                {multiSelectedCount}
                            </span>
                        )}
                    </Button>
                    {isMultiSelectMode && multiSelectedCount > 0 && (
                        <Button
                            variant="outline"
                            size="sm"
                            className={cn(
                                'h-9 gap-2 rounded-xl',
                                'bg-red-500 hover:bg-red-600 text-white border-red-500',
                                'font-semibold'
                            )}
                            onClick={onDeleteSelected}
                            title={t('designMode.toolbar.deleteSelected')}
                        >
                            <Trash2 className="h-4 w-4" />
                            <span className="text-xs">
                                {t('designMode.toolbar.delete')}
                            </span>
                        </Button>
                    )}
                    <div className="w-px h-5 bg-white/10" />
                </>
            )}

            {/* Spacer */}
            <div className="flex-1" />

            {/* Changes Button */}
            {isEnabled && (
                <>
                    <Button
                        variant="outline"
                        size="sm"
                        className={cn(
                            'h-9 gap-2 rounded-xl',
                            'border-white/10 bg-[#202927] text-white/80',
                            'hover:bg-[#24302e] hover:text-white hover:border-white/30',
                            pendingChanges.length > 0 &&
                                'border-[#a6ffff]/50 bg-[#a6ffff]/10'
                        )}
                        onClick={onOpenChangesPanel}
                    >
                        <Undo2 className="h-4 w-4" />
                        <span className="text-xs font-semibold">
                            {t('designMode.toolbar.changes')}
                        </span>
                        {pendingChanges.length > 0 && (
                            <span className="px-1.5 py-0.5 bg-[#a6ffff] text-[#181e1c] rounded-full text-[10px] font-bold min-w-[18px] text-center">
                                {pendingChanges.length}
                            </span>
                        )}
                    </Button>
                    <Button
                        size="sm"
                        className={cn(
                            'h-9 gap-2 rounded-xl',
                            'bg-[#a6ffff] hover:bg-[#a6ffff]/90 text-[#181e1c] font-semibold'
                        )}
                        onClick={onSaveClick}
                        disabled={pendingChanges.length === 0 || isSaving}
                    >
                        {isSaving ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin" />
                                <span className="text-xs">
                                    {t('designMode.toolbar.syncing')}
                                    {syncProgress
                                        ? ` ${syncProgress.processed}/${syncProgress.total}`
                                        : ''}
                                </span>
                            </>
                        ) : (
                            <span className="text-xs">{t('common.save')}</span>
                        )}
                    </Button>
                </>
            )}
        </div>
    )
}
