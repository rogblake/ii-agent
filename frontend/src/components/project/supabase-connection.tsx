import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { ComposioManageModal } from '@/components/composio/composio-manage-modal'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
    type ComposioProfile,
    useConnectToolkitMutation,
    useDeleteProfileMutation,
    useEnableProfileMutation,
    useGetComposioProfilesQuery
} from '@/state/api/composio.api'

const SUPABASE_TOOLKIT_SLUG = 'supabase'

const OAUTH_WINDOW_CONFIG = {
    width: 600,
    height: 700,
    pollInterval: 500,
    timeout: 5 * 60 * 1000
}

function getProfilePriority(status: string): number {
    switch (status) {
        case 'enable':
            return 0
        case 'disable':
            return 1
        case 'disconnected':
            return 2
        case 'pending':
            return 3
        default:
            return 4
    }
}

function pickPreferredProfile(
    profiles: ComposioProfile[]
): ComposioProfile | null {
    if (profiles.length === 0) {
        return null
    }

    return [...profiles].sort(
        (left, right) =>
            getProfilePriority(left.status) - getProfilePriority(right.status)
    )[0]
}

function getAllowedOrigins(): Set<string> {
    const allowedOrigins = new Set([window.location.origin])

    try {
        const apiUrl = import.meta.env.VITE_API_URL
        if (apiUrl) {
            allowedOrigins.add(new URL(apiUrl).origin)
        }
    } catch (error) {
        console.warn('Invalid API URL provided in VITE_API_URL:', error)
    }

    return allowedOrigins
}

type SupabaseConnectionVariant = 'settings' | 'project'

interface SupabaseConnectionProps {
    variant?: SupabaseConnectionVariant
}

export const SupabaseConnection = ({ variant = 'project' }: SupabaseConnectionProps) => {
    const { t } = useTranslation()
    const [isConnecting, setIsConnecting] = useState(false)
    const [isDisconnecting, setIsDisconnecting] = useState(false)
    const [isEnabling, setIsEnabling] = useState(false)
    const [manageModalOpen, setManageModalOpen] = useState(false)

    const {
        data: profilesData,
        isLoading: isLoadingProfiles,
        refetch: refetchProfiles
    } = useGetComposioProfilesQuery()
    const [connectToolkit] = useConnectToolkitMutation()
    const [deleteProfile] = useDeleteProfileMutation()
    const [enableProfile] = useEnableProfileMutation()

    const appName = t('project.integrations.supabase.title')
    const supabaseProfiles = (profilesData?.profiles ?? []).filter(
        (profile) => profile.toolkit_slug === SUPABASE_TOOLKIT_SLUG
    )
    const profile = pickPreferredProfile(supabaseProfiles)

    const isConnected = profile?.status === 'enable'
    const isDisabled = profile?.status === 'disable'
    const isDisconnected = profile?.status === 'disconnected'
    const isPending = profile?.status === 'pending'
    const isBusy = isConnecting || isDisconnecting || isEnabling

    const waitForOAuthCompletion = (redirectUrl: string) =>
        new Promise<void>((resolve, reject) => {
            const allowedOrigins = getAllowedOrigins()
            let popup: Window | null = null
            let completed = false
            let pollTimer: number | null = null
            let timeoutId: number | null = null

            const finish = (callback: () => void) => {
                if (completed) {
                    return
                }

                completed = true
                if (pollTimer) {
                    window.clearInterval(pollTimer)
                }
                if (timeoutId) {
                    window.clearTimeout(timeoutId)
                }
                window.removeEventListener('message', handleMessage)

                try {
                    popup?.close()
                } catch (error) {
                    console.warn('Failed to close popup window:', error)
                }

                callback()
            }

            const handleMessage = (
                event: MessageEvent<{
                    type?: string
                    appName?: string
                    error?: string
                }>
            ) => {
                if (!allowedOrigins.has(event.origin)) {
                    return
                }

                if (event.data?.type !== 'composio-auth') {
                    return
                }

                if (
                    event.data.appName &&
                    event.data.appName !== SUPABASE_TOOLKIT_SLUG
                ) {
                    return
                }

                if (event.data.error) {
                    finish(() => reject(new Error(event.data.error)))
                    return
                }

                finish(resolve)
            }

            window.addEventListener('message', handleMessage)

            const { width, height, pollInterval, timeout } = OAUTH_WINDOW_CONFIG
            const left = window.screen.width / 2 - width / 2
            const top = window.screen.height / 2 - height / 2

            popup = window.open(
                redirectUrl,
                '_blank',
                `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
            )

            if (!popup) {
                finish(() =>
                    reject(
                        new Error(
                            t(
                                'composio.integrationsModal.toasts.couldNotOpenAuthWindow',
                                { appName }
                            )
                        )
                    )
                )
                return
            }

            pollTimer = window.setInterval(() => {
                if (popup && popup.closed) {
                    finish(() =>
                        reject(
                            new Error(
                                t(
                                    'composio.integrationsModal.toasts.connectionTimedOut',
                                    { appName }
                                )
                            )
                        )
                    )
                }
            }, pollInterval)

            timeoutId = window.setTimeout(() => {
                finish(() =>
                    reject(
                        new Error(
                            t(
                                'composio.integrationsModal.toasts.connectionTimedOut',
                                { appName }
                            )
                        )
                    )
                )
            }, timeout)
        })

    const handleConnect = async () => {
        if (isBusy) {
            return
        }

        setIsConnecting(true)
        try {
            const result = await connectToolkit({
                toolkitSlug: SUPABASE_TOOLKIT_SLUG,
                request: {
                    profile_name: `Project ${appName}`,
                    initiation_fields: {}
                }
            }).unwrap()

            if (result.redirect_url) {
                await waitForOAuthCompletion(result.redirect_url)
            } else if (!result.success) {
                throw new Error(
                    result.message ||
                        t(
                            'composio.integrationsModal.toasts.connectionNotCompleted',
                            { appName }
                        )
                )
            }

            await refetchProfiles()
            toast.success(
                t('composio.integrationsModal.toasts.connectedSuccess', {
                    appName
                }),
                {
                    description: t(
                        'composio.integrationsModal.toasts.connectedDescription'
                    )
                }
            )
        } catch (error) {
            console.error('Failed to connect Supabase', error)
            toast.error(
                error instanceof Error
                    ? error.message
                    : t('composio.integrationsModal.toasts.failedToConnect', {
                          appName
                      })
            )
        } finally {
            setIsConnecting(false)
        }
    }

    const handleEnable = async () => {
        if (!profile || isBusy) {
            return
        }

        setIsEnabling(true)
        try {
            await enableProfile(profile.id).unwrap()
            toast.success(
                t('composio.integrationsModal.toasts.connectedSuccess', {
                    appName
                }),
                {
                    description: t(
                        'composio.integrationsModal.toasts.connectedDescription'
                    )
                }
            )
        } catch (error) {
            console.error('Failed to enable Supabase', error)
            toast.error(
                error instanceof Error
                    ? error.message
                    : t('composio.integrationsModal.toasts.failedToConnect', {
                          appName
                      })
            )
        } finally {
            setIsEnabling(false)
        }
    }

    const handleDisconnect = async () => {
        if (!profile || isBusy) {
            return
        }

        setIsDisconnecting(true)
        try {
            await deleteProfile(profile.id).unwrap()
            toast.success(
                t('composio.integrationsModal.toasts.disconnectedSuccess', {
                    appName
                }),
                {
                    description: t(
                        'composio.integrationsModal.toasts.disconnectedDescription'
                    )
                }
            )
        } catch (error) {
            console.error('Failed to disconnect Supabase', error)
            toast.error(
                error instanceof Error
                    ? error.message
                    : t(
                          'composio.integrationsModal.toasts.failedToDisconnect',
                          { appName }
                      )
            )
        } finally {
            setIsDisconnecting(false)
        }
    }

    const handlePrimaryAction = () => {
        if (!profile || isPending || isDisconnected) {
            void handleConnect()
            return
        }

        if (isConnected) {
            setManageModalOpen(true)
            return
        }

        if (isDisabled) {
            void handleEnable()
        }
    }

    const primaryLabel = (() => {
        if (isConnecting) {
            return t('connectors.status.connecting')
        }
        if (isEnabling) {
            return t('connectors.status.connecting')
        }
        if (!profile || isPending || isDisconnected) {
            return t('composio.appCard.connect')
        }
        if (isConnected) {
            return t('composio.appCard.manage')
        }
        return t('composio.appCard.enable')
    })()

    const secondaryLabel = isDisconnecting
        ? t('connectors.status.disconnecting')
        : t('composio.manageModal.disconnect')

    const statusLabel = (() => {
        if (isLoadingProfiles && !profilesData) {
            return t('connectors.status.checking')
        }
        if (isConnecting || isPending) {
            return t('connectors.status.connecting')
        }
        if (isConnected) {
            return t('composio.appCard.status.connected')
        }
        if (profile?.status === 'disable') {
            return t('composio.appCard.status.disabled')
        }
        return t('project.integrations.status.notConnected')
    })()

    const settingsButtonLabel = (() => {
        if (isLoadingProfiles && !profilesData) return t('connectors.status.checking')
        if (isConnecting || isEnabling) return t('connectors.status.connecting')
        if (isDisconnecting) return t('connectors.status.disconnecting')
        if (isConnected) return t('composio.manageModal.disconnect')
        return t('composio.appCard.connect')
    })()

    if (variant === 'settings') {
        return (
            <>
                <div className="flex items-center justify-between">
                    <div className="space-y-1">
                        <p className="text-sm">{appName}</p>
                        <p className="text-xs text-black/60 dark:text-white/60">
                            {t('project.integrations.supabase.description')}
                        </p>
                    </div>
                    <Button
                        className={cn(
                            'underline p-0 h-auto text-black/[0.56] dark:text-white/[0.56]',
                            isConnected && 'text-red-600 dark:text-red-400'
                        )}
                        disabled={isBusy || (isLoadingProfiles && !profilesData)}
                        onClick={
                            isConnected
                                ? () => void handleDisconnect()
                                : handlePrimaryAction
                        }
                    >
                        {settingsButtonLabel}
                    </Button>
                </div>
                {profile ? (
                    <ComposioManageModal
                        open={manageModalOpen}
                        onOpenChange={setManageModalOpen}
                        profile={profile}
                        onDisconnect={handleDisconnect}
                    />
                ) : null}
            </>
        )
    }

    return (
        <>
            <div className="rounded-2xl border border-black/10 bg-firefly/5 p-5 dark:border-white/10 dark:bg-sky-blue-2/5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex items-center gap-4">
                        <img
                            src="/images/supabase.svg"
                            alt="Supabase"
                            className="size-12"
                        />
                        <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                                <p className="text-base font-semibold text-black dark:text-white">
                                    {appName}
                                </p>
                                <Badge
                                    variant="outline"
                                    className={cn(
                                        'border-black/10 bg-white/70 text-black dark:border-white/10 dark:bg-white/5 dark:text-white',
                                        isConnected &&
                                            'border-emerald-600/30 text-emerald-700 dark:text-emerald-400',
                                        (isConnecting || isPending) &&
                                            'border-sky-500/30 text-sky-700 dark:text-sky-300'
                                    )}
                                >
                                    {statusLabel}
                                </Badge>
                            </div>
                            <p className="text-sm text-black/65 dark:text-white/65">
                                {t('project.integrations.supabase.description')}
                            </p>
                            <p className="text-xs text-black/55 dark:text-white/55">
                                {t('project.integrations.supabase.helper')}
                            </p>
                        </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                        <Button
                            className={cn(
                                'rounded-full px-4 bg-firefly text-sky-blue-2 hover:bg-firefly/90 dark:bg-sky-blue dark:text-black dark:hover:bg-sky-blue/90'
                            )}
                            disabled={
                                isBusy || (isLoadingProfiles && !profilesData)
                            }
                            onClick={handlePrimaryAction}
                        >
                            {primaryLabel}
                        </Button>
                        {profile ? (
                            <Button
                                variant="outline"
                                className="rounded-full px-4 text-red-2 border-red-2"
                                disabled={isBusy}
                                onClick={() => void handleDisconnect()}
                            >
                                {secondaryLabel}
                            </Button>
                        ) : null}
                    </div>
                </div>
            </div>

            {profile ? (
                <ComposioManageModal
                    open={manageModalOpen}
                    onOpenChange={setManageModalOpen}
                    profile={profile}
                    onDisconnect={handleDisconnect}
                />
            ) : null}
        </>
    )
}
