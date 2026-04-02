/**
 * Nano Banana Version Selector Component
 *
 * Displays version history dropdown for slide versions.
 * Follows the same pattern as StorybookVersionSelector.
 */

import { useCallback } from 'react'
import { History, ChevronDown, Check, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import type { SlideVersionInfo } from './types'

interface NanoBananaVersionSelectorProps {
    versions: SlideVersionInfo[]
    currentVersionId: string | null
    onVersionSelect: (versionId: string) => void
    isLoading?: boolean
    isReverting?: boolean
    disabled?: boolean
    className?: string
}

export function NanoBananaVersionSelector({
    versions,
    currentVersionId,
    onVersionSelect,
    isLoading = false,
    isReverting = false,
    disabled = false,
    className
}: NanoBananaVersionSelectorProps) {
    const { t } = useTranslation()

    const handleVersionSelect = useCallback(
        (version: SlideVersionInfo) => {
            if (version.id === currentVersionId) return
            onVersionSelect(version.id)
        },
        [currentVersionId, onVersionSelect]
    )

    // Get version label
    const getVersionLabel = (version: SlideVersionInfo) => {
        if (version.version === 1) {
            return `Original (v${version.version})`
        }
        if (version.is_current) {
            return `Current (v${version.version})`
        }
        return `Version ${version.version}`
    }

    // Format the date
    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return ''
        try {
            const date = new Date(dateStr)
            return date.toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            })
        } catch {
            return ''
        }
    }

    // Find current version
    const currentVersion = versions.find((v) => v.id === currentVersionId)

    // Don't show if only one version or no versions
    if (versions.length <= 1) {
        return null
    }

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild disabled={disabled || isReverting}>
                <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                        'gap-1.5 text-muted-foreground',
                        className
                    )}
                >
                    {isReverting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <History className="h-4 w-4" />
                    )}
                    <span>
                        {currentVersion
                            ? `v${currentVersion.version}`
                            : t('common.version', 'Version')}
                    </span>
                    <ChevronDown className="h-3 w-3" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                    {t('designMode.versionHistory', 'Version History')}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />

                {isLoading ? (
                    <div className="flex items-center justify-center py-4">
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    </div>
                ) : versions.length === 0 ? (
                    <div className="px-2 py-2 text-xs text-muted-foreground">
                        No versions found
                    </div>
                ) : (
                    versions.map((version) => (
                        <DropdownMenuItem
                            key={version.id}
                            className="flex items-center justify-between cursor-pointer"
                            onClick={() => handleVersionSelect(version)}
                        >
                            <div className="flex flex-col gap-0.5">
                                <span className="text-sm font-medium">
                                    {getVersionLabel(version)}
                                </span>
                                {version.edit_summary && (
                                    <span className="text-xs text-muted-foreground truncate max-w-[180px]">
                                        {version.edit_summary}
                                    </span>
                                )}
                                {version.created_at && (
                                    <span className="text-xs text-muted-foreground">
                                        {formatDate(version.created_at)}
                                    </span>
                                )}
                            </div>
                            {version.id === currentVersionId && (
                                <Check className="h-4 w-4 text-primary flex-shrink-0" />
                            )}
                        </DropdownMenuItem>
                    ))
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
