import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { ComposioToolkit, ComposioProfile } from '@/state/api/composio.api'
import {
    useEnableProfileMutation,
    useDisableProfileMutation
} from '@/state/api/composio.api'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'

interface ComposioAppCardProps {
    app: ComposioToolkit
    profiles: ComposioProfile[]
    onConnect: () => void
    onManage?: (profile: ComposioProfile) => void
    isConnecting?: boolean
}

function ComposioAppCard({
    app,
    profiles,
    onConnect,
    onManage,
    isConnecting = false
}: ComposioAppCardProps) {
    const { t } = useTranslation()
    const [imageError, setImageError] = useState(false)
    const connectedProfile = profiles.find((p) => p.status === 'enable')
    const disabledProfile = profiles.find((p) => p.status === 'disable')
    const isConnected = Boolean(connectedProfile)
    const showLogo = app.logo && !imageError

    // Only consider 'enable' or 'disable' profiles as valid, ignore 'pending'
    const anyProfile = connectedProfile || disabledProfile
    const hasProfiles = Boolean(anyProfile)

    // Local state to track connection status optimistically
    const [localIsConnected, setLocalIsConnected] = useState<boolean | null>(
        null
    )

    // Use local state if available, otherwise use props
    const effectiveIsConnected =
        localIsConnected !== null ? localIsConnected : isConnected

    const [enableProfile, { isLoading: isEnabling }] =
        useEnableProfileMutation()
    const [disableProfile, { isLoading: isDisabling }] =
        useDisableProfileMutation()

    // Reset local state when profiles prop changes (after refetch)
    useEffect(() => {
        if (localIsConnected !== null) {
            // After API refetch completes, reset local state to sync with server
            const timer = setTimeout(() => {
                setLocalIsConnected(null)
            }, 100)
            return () => clearTimeout(timer)
        }
    }, [isConnected, localIsConnected])

    const handleButtonClick = () => {
        if (hasProfiles && anyProfile) {
            // If user has any profile (enabled or disabled), open manage
            onManage?.(anyProfile)
        } else {
            // No profile exists, initiate connection
            onConnect()
        }
    }

    const handleToggleStatus = async () => {
        if (!anyProfile) return

        try {
            if (effectiveIsConnected) {
                // Optimistically update UI
                setLocalIsConnected(false)
                await disableProfile(anyProfile.id).unwrap()
                toast.success(
                    t('composio.appCard.status.disabled') + `: ${app.name}`
                )
            } else {
                // Optimistically update UI
                setLocalIsConnected(true)
                await enableProfile(anyProfile.id).unwrap()
                toast.success(
                    t('composio.appCard.status.connected') + `: ${app.name}`
                )
            }
        } catch (error: any) {
            // Revert optimistic update on error
            setLocalIsConnected(null)
            toast.error(
                error.message ||
                    t('composio.manageModal.toasts.failedToUpdateTools')
            )
        }
    }

    const getButtonText = () => {
        if (isConnecting) return t('composio.appCard.connecting')
        if (hasProfiles) return t('composio.appCard.manage')
        return t('composio.appCard.connect')
    }

    return (
        <div
            className="group relative rounded-xl border border-gray-200 bg-white hover:border-gray-300 transition-all hover:shadow-lg flex flex-col h-full"
            role="article"
            aria-label={t('composio.appCard.aria.integrationCard', {
                appName: app.name
            })}
        >
            <div className="p-6 flex flex-col flex-1">
                {/* Header */}
                <div className="flex items-start gap-4 mb-5">
                    <div
                        className="relative h-14 w-14 rounded-xl overflow-hidden bg-gradient-to-br from-gray-50 to-gray-100 flex-shrink-0 ring-1 ring-gray-200"
                        aria-hidden="true"
                    >
                        {showLogo ? (
                            <img
                                src={app.logo}
                                alt={`${app.name} logo`}
                                className="h-full w-full object-cover"
                                onError={() => setImageError(true)}
                            />
                        ) : (
                            <div className="h-full w-full flex items-center justify-center text-gray-600 font-semibold text-lg">
                                {app.name.charAt(0).toUpperCase()}
                            </div>
                        )}
                    </div>
                    <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-lg text-gray-900 mb-1.5 leading-tight">
                            {app.name}
                        </h3>
                        <div className="flex items-center gap-2">
                            {isConnecting ? (
                                <Badge className="bg-blue-50 text-violet border-violet text-xs px-2 py-0.5 font-medium">
                                    ● {t('composio.appCard.status.connecting')}
                                </Badge>
                            ) : hasProfiles && effectiveIsConnected ? (
                                <Badge className="bg-emerald-50 text-green border-green text-xs px-2 py-0.5 font-medium">
                                    ● {t('composio.appCard.status.connected')}
                                </Badge>
                            ) : anyProfile?.status === 'disable' ? (
                                <Badge className="bg-gray-100 text-gray-600 border-gray-200 text-xs px-2 py-0.5 font-medium">
                                    ● {t('composio.appCard.status.disabled')}
                                </Badge>
                            ) : (
                                <Badge className="bg-gray-100 text-gray-600 border-gray-200 text-xs px-2 py-0.5 font-medium">
                                    ●{' '}
                                    {t('composio.appCard.status.disconnected')}
                                </Badge>
                            )}
                        </div>
                    </div>
                </div>

                {/* Description */}
                <div className="flex-1 mb-4">
                    <p className="text-sm text-gray-600 line-clamp-3 leading-relaxed">
                        {app.description ||
                            `Connect to ${app.name} and access its tools and capabilities.`}
                    </p>
                </div>

                {/* Tags */}
                {/* {app.tags && app.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-4">
                        {app.tags.slice(0, 3).map((tag, index) => (
                            <Badge
                                key={index}
                                variant="secondary"
                                className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-0 font-normal"
                            >
                                {tag}
                            </Badge>
                        ))}
                        {app.tags.length > 3 && (
                            <Badge
                                variant="secondary"
                                className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-0 font-normal"
                            >
                                +{app.tags.length - 3}
                            </Badge>
                        )}
                    </div>
                )} */}

                {/* Buttons */}
                <div className="flex gap-2">
                    {hasProfiles && !isConnecting && (
                        <Button
                            onClick={handleToggleStatus}
                            disabled={isEnabling || isDisabling || isConnecting}
                            variant="outline"
                            className={`h-11 px-4 font-medium transition-all text-sm ${
                                effectiveIsConnected
                                    ? 'border-black/30 text-black'
                                    : 'border-black text-black'
                            }`}
                        >
                            {isEnabling || isDisabling ? (
                                <span className="flex items-center gap-2">
                                    <span className="w-3 h-3 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                                </span>
                            ) : effectiveIsConnected ? (
                                t('composio.appCard.disable')
                            ) : (
                                t('composio.appCard.enable')
                            )}
                        </Button>
                    )}

                    <Button
                        onClick={handleButtonClick}
                        disabled={isConnecting}
                        aria-label={
                            hasProfiles
                                ? t('composio.appCard.aria.manageConnection', {
                                      appName: app.name
                                  })
                                : t('composio.appCard.aria.connectApp', {
                                      appName: app.name
                                  })
                        }
                        className={`flex-1 h-11 font-medium transition-all text-base ${
                            hasProfiles
                                ? 'bg-firefly text-sky-blue-2'
                                : 'bg-sky-blue text-black'
                        }`}
                    >
                        {isConnecting ? (
                            <span className="flex items-center gap-2">
                                {t('composio.appCard.connecting')}
                            </span>
                        ) : (
                            getButtonText()
                        )}
                    </Button>
                </div>
            </div>
        </div>
    )
}

export default ComposioAppCard
