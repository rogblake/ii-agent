/**
 * Storybook Version Selector Component
 *
 * Displays version history dropdown and allows switching between versions.
 */

import { useCallback, useEffect, useState } from 'react'
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
import { storybookService, type VersionInfo } from '@/services/storybook.service'

interface StorybookVersionSelectorProps {
    storybookId: string
    currentVersion: number
    onVersionSelect: (storybookId: string, version: number) => void
    disabled?: boolean
    className?: string
}

export function StorybookVersionSelector({
    storybookId,
    currentVersion,
    onVersionSelect,
    disabled = false,
    className
}: StorybookVersionSelectorProps) {
    const { t } = useTranslation()
    const [versions, setVersions] = useState<VersionInfo[]>([])
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [isOpen, setIsOpen] = useState(false)

    // Load version history when dropdown opens
    const loadVersionHistory = useCallback(async () => {
        if (versions.length > 0) return // Already loaded

        setIsLoading(true)
        setError(null)

        try {
            const response = await storybookService.getVersionHistory(storybookId)
            setVersions(response.versions)
        } catch (err) {
            console.error('[VersionSelector] Failed to load versions:', err)
            setError(t('storybook.versionSelector.loadError'))
        } finally {
            setIsLoading(false)
        }
    }, [storybookId, versions.length, t])

    // Load versions when dropdown opens
    useEffect(() => {
        if (isOpen) {
            loadVersionHistory()
        }
    }, [isOpen, loadVersionHistory])

    // Reset versions when storybook changes
    useEffect(() => {
        setVersions([])
    }, [storybookId])

    const handleVersionSelect = useCallback(
        (version: VersionInfo) => {
            if (version.version === currentVersion) return
            onVersionSelect(version.id, version.version)
            setIsOpen(false)
        },
        [currentVersion, onVersionSelect]
    )

    // Format the version label
    const getVersionLabel = (version: VersionInfo) => {
        const label = t('storybook.versionSelector.versionLabel', {
            version: version.version
        })
        if (version.version === 1) {
            return t('storybook.versionSelector.originalLabel', {
                version: version.version
            })
        }
        if (version.is_current) {
            return t('storybook.versionSelector.currentLabel', {
                version: version.version
            })
        }
        return label
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

    // If only one version exists (v1), don't show the selector
    if (currentVersion === 1 && versions.length <= 1 && !isOpen) {
        return null
    }

    return (
        <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
            <DropdownMenuTrigger asChild disabled={disabled}>
                <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                        'gap-1.5 text-muted-foreground',
                        className
                    )}
                >
                    <History className="h-4 w-4" />
                    <span>
                        {t('storybook.versionSelector.versionLabel', {
                            version: currentVersion
                        })}
                    </span>
                    <ChevronDown className="h-3 w-3" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                    {t('storybook.versionSelector.title')}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />

                {isLoading ? (
                    <div className="flex items-center justify-center py-4">
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    </div>
                ) : error ? (
                    <div className="px-2 py-2 text-xs text-destructive">
                        {error}
                    </div>
                ) : versions.length === 0 ? (
                    <div className="px-2 py-2 text-xs text-muted-foreground">
                        {t('storybook.versionSelector.noVersions')}
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
                                {version.created_at && (
                                    <span className="text-xs text-muted-foreground">
                                        {formatDate(version.created_at)}
                                    </span>
                                )}
                            </div>
                            {version.version === currentVersion && (
                                <Check className="h-4 w-4 text-primary" />
                            )}
                        </DropdownMenuItem>
                    ))
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

export type { StorybookVersionSelectorProps }
