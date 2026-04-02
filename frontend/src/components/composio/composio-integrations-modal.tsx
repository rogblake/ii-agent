import { useState, useMemo, useEffect } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
    useGetComposioToolkitsQuery,
    useGetComposioProfilesQuery,
    useConnectToolkitMutation,
    useDeleteProfileMutation,
    type ComposioToolkit,
    type ComposioProfile
} from '@/state/api/composio.api'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription
} from '../ui/dialog'
import { Input } from '../ui/input'
import { Icon } from '../ui/icon'
import { Skeleton } from '../ui/skeleton'
// import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import ComposioAppCard from './composio-app-card'
import { ComposioManageModal } from './composio-manage-modal'

// Popular apps to prioritize in the list
const POPULAR_APPS = ['gmail', 'slack', 'googlecalendar', 'notion', 'github']

// OAuth window configuration
const OAUTH_WINDOW_CONFIG = {
    width: 600,
    height: 700,
    pollInterval: 500,
    timeout: 5 * 60 * 1000 // 5 minutes
}

interface ComposioIntegrationsModalProps {
    open: boolean
    onOpenChange: (open: boolean) => void
}

function AppCardSkeleton() {
    return (
        <div className="border border-gray-200 rounded-xl p-6 bg-white">
            <div className="flex items-center gap-4 mb-5">
                <Skeleton className="w-14 h-14 rounded-xl bg-gray-200" />
                <div className="flex-1">
                    <Skeleton className="w-3/4 h-6 mb-2 bg-gray-200" />
                    <Skeleton className="w-1/2 h-4 bg-gray-200" />
                </div>
            </div>
            <Skeleton className="w-full h-12 mb-4 bg-gray-200" />
            <Skeleton className="w-full h-10 mb-3 bg-gray-200" />
            <div className="flex gap-2 mb-4">
                <Skeleton className="w-20 h-6 rounded-md bg-gray-200" />
                <Skeleton className="w-24 h-6 rounded-md bg-gray-200" />
                <Skeleton className="w-16 h-6 rounded-md bg-gray-200" />
            </div>
            <Skeleton className="w-full h-11 rounded-lg bg-gray-200" />
        </div>
    )
}

function groupProfilesByToolkit(
    profiles: ComposioProfile[]
): Record<string, ComposioProfile[]> {
    const grouped: Record<string, ComposioProfile[]> = {}
    for (const profile of profiles) {
        if (!grouped[profile.toolkit_slug]) {
            grouped[profile.toolkit_slug] = []
        }
        grouped[profile.toolkit_slug].push(profile)
    }
    return grouped
}

function sortToolkits(toolkits: ComposioToolkit[]): ComposioToolkit[] {
    return [...toolkits].sort((a, b) => {
        const aPopularIndex = POPULAR_APPS.indexOf(a.slug)
        const bPopularIndex = POPULAR_APPS.indexOf(b.slug)

        // Both are popular - sort by popularity order
        if (aPopularIndex !== -1 && bPopularIndex !== -1) {
            return aPopularIndex - bPopularIndex
        }
        // Only a is popular
        if (aPopularIndex !== -1) return -1
        // Only b is popular
        if (bPopularIndex !== -1) return 1

        // Neither is popular - sort alphabetically
        return a.name.localeCompare(b.name)
    })
}

function ComposioIntegrationsModal({
    open,
    onOpenChange
}: ComposioIntegrationsModalProps) {
    const { t } = useTranslation()
    const [search, setSearch] = useState('')
    const [debouncedSearch, setDebouncedSearch] = useState('')
    const [connectingApp, setConnectingApp] = useState<string | null>(null)
    const [managingProfile, setManagingProfile] =
        useState<ComposioProfile | null>(null)

    // Debounce search input
    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedSearch(search)
        }, 300)
        return () => clearTimeout(timer)
    }, [search])

    const { data: toolkitsData, isLoading: isLoadingToolkits } =
        useGetComposioToolkitsQuery({ search: debouncedSearch, limit: 100 })

    const {
        data: profilesData,
        isLoading: isLoadingProfiles,
        refetch: refetchProfiles
    } = useGetComposioProfilesQuery()

    const [connectToolkit] = useConnectToolkitMutation()
    const [deleteProfile] = useDeleteProfileMutation()

    const toolkits = toolkitsData?.toolkits || []
    const profiles = profilesData?.profiles || []

    const profilesByToolkit = useMemo(
        () => groupProfilesByToolkit(profiles),
        [profiles]
    )

    const sortedToolkits = useMemo(() => sortToolkits(toolkits), [toolkits])

    // No category filters for now; show sorted list
    const filteredToolkits = sortedToolkits

    const isLoading = isLoadingToolkits || isLoadingProfiles

    const openOAuthWindow = (redirectUrl: string): Window | null => {
        const { width, height } = OAUTH_WINDOW_CONFIG
        const left = window.screen.width / 2 - width / 2
        const top = window.screen.height / 2 - height / 2

        return window.open(
            redirectUrl,
            '_blank',
            `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
        )
    }

    const handleConnect = async (app: ComposioToolkit) => {
        setConnectingApp(app.slug)

        const checkConnection = async () => {
            const refreshed = await refetchProfiles()
            const updatedProfiles = refreshed.data?.profiles || []
            // Check if connection is completed (enable) or still pending
            const profile = updatedProfiles.find(
                (p) => p.toolkit_slug === app.slug
            )
            return profile?.status === 'enable'
        }

        try {
            const result = await connectToolkit({
                toolkitSlug: app.slug,
                request: {
                    profile_name: `My ${app.name}`,
                    initiation_fields: {}
                }
            }).unwrap()

            if (result.redirect_url) {
                const authWindow = openOAuthWindow(result.redirect_url)
                if (!authWindow) {
                    toast.error(
                        t(
                            'composio.integrationsModal.toasts.couldNotOpenAuthWindow',
                            { appName: app.name }
                        ),
                        {
                            description: t(
                                'composio.integrationsModal.toasts.allowPopupsDescription'
                            )
                        }
                    )
                    setConnectingApp(null)
                    return
                }

                let completed = false
                let pollTimer: number | null = null
                let timeoutId: number | null = null

                const finish = (fn: () => void) => {
                    if (completed) return
                    completed = true
                    if (pollTimer) window.clearInterval(pollTimer)
                    if (timeoutId) window.clearTimeout(timeoutId)
                    window.removeEventListener('message', messageHandler)
                    setConnectingApp(null)
                    fn()
                }

                // Listen for OAuth completion messages from popup
                const messageHandler = async (event: MessageEvent) => {
                    // Verify origin (accept from same origin or API URL)
                    const allowedOrigins = new Set([window.location.origin])
                    try {
                        const apiUrl = import.meta.env.VITE_API_URL
                        if (apiUrl) {
                            allowedOrigins.add(new URL(apiUrl).origin)
                        }
                    } catch {
                        // Ignore invalid API URL
                    }

                    if (!allowedOrigins.has(event.origin)) return

                    // const data = event.data
                    // if (data && data.type === 'composio-auth') {
                    //     if (data.success && data.appName === app.slug) {
                    //         // Stop polling immediately to prevent race condition
                    //         if (pollTimer) window.clearInterval(pollTimer)

                    //         // Wait a bit for database to update
                    //         await new Promise(resolve => setTimeout(resolve, 500))

                    //         // Refetch profiles to update UI immediately
                    //         await refetchProfiles()

                    //         finish(() => {
                    //             toast.success(`${app.name} connected successfully!`, {
                    //                 description: 'You can now use this integration'
                    //             })
                    //         })
                    //     } else if (data.error) {
                    //         finish(() => {
                    //             toast.error(`Failed to connect ${app.name}`, {
                    //                 description: data.error
                    //             })
                    //         })
                    //     }
                    // }
                }

                window.addEventListener('message', messageHandler)

                // Poll for window close (fallback if message doesn't arrive)
                pollTimer = window.setInterval(async () => {
                    if (authWindow && authWindow.closed) {
                        // Don't proceed if already completed
                        if (completed) return

                        if (pollTimer) window.clearInterval(pollTimer)

                        // Wait a bit for database to update after OAuth callback
                        await new Promise((resolve) =>
                            setTimeout(resolve, 1000)
                        )

                        const isConnected = await checkConnection()
                        finish(() => {
                            if (isConnected) {
                                toast.success(
                                    t(
                                        'composio.integrationsModal.toasts.connectedSuccess',
                                        { appName: app.name }
                                    ),
                                    {
                                        description: t(
                                            'composio.integrationsModal.toasts.connectedDescription'
                                        )
                                    }
                                )
                            } else {
                                toast.error(
                                    t(
                                        'composio.integrationsModal.toasts.connectionNotCompleted',
                                        { appName: app.name }
                                    ),
                                    {
                                        description: t(
                                            'composio.integrationsModal.toasts.connectionNotCompletedDescription'
                                        )
                                    }
                                )
                            }
                        })
                    }
                }, OAUTH_WINDOW_CONFIG.pollInterval)

                // Timeout after configured duration
                timeoutId = window.setTimeout(() => {
                    if (pollTimer) window.clearInterval(pollTimer)
                    if (authWindow && !authWindow.closed) {
                        authWindow.close()
                    }
                    finish(() => {
                        toast.error(
                            t(
                                'composio.integrationsModal.toasts.connectionTimedOut',
                                { appName: app.name }
                            ),
                            {
                                description: t(
                                    'composio.integrationsModal.toasts.connectionTimedOutDescription'
                                ),
                                action: {
                                    label: t('common.retry'),
                                    onClick: () => handleConnect(app)
                                }
                            }
                        )
                    })
                }, OAUTH_WINDOW_CONFIG.timeout)
            } else {
                const isConnected = await checkConnection()
                if (isConnected) {
                    toast.success(
                        t(
                            'composio.integrationsModal.toasts.connectedSuccess',
                            { appName: app.name }
                        ),
                        {
                            description: t(
                                'composio.integrationsModal.toasts.connectedDescription'
                            )
                        }
                    )
                } else {
                    toast.error(
                        t(
                            'composio.integrationsModal.toasts.connectionNotCompleted',
                            { appName: app.name }
                        ),
                        {
                            description: t(
                                'composio.integrationsModal.toasts.connectionNotCompletedDescription'
                            )
                        }
                    )
                }
                setConnectingApp(null)
            }
        } catch (error: unknown) {
            console.error('Failed to connect toolkit:', error)
            const errorMessage =
                (error as { data?: { error?: string } })?.data?.error ||
                t('composio.integrationsModal.toasts.failedToConnect', {
                    appName: app.name
                })
            toast.error(
                t('composio.integrationsModal.toasts.failedToConnect', {
                    appName: app.name
                }),
                {
                    description: errorMessage,
                    action: {
                        label: t('common.retry'),
                        onClick: () => handleConnect(app)
                    }
                }
            )
            setConnectingApp(null)
        }
    }

    const handleDisconnect = async () => {
        if (!managingProfile) return

        try {
            await deleteProfile(managingProfile.id).unwrap()

            // Force refetch profiles to update UI immediately
            await refetchProfiles()

            toast.success(
                t('composio.integrationsModal.toasts.disconnectedSuccess', {
                    appName: managingProfile.toolkit_name
                }),
                {
                    description: t(
                        'composio.integrationsModal.toasts.disconnectedDescription'
                    )
                }
            )
            setManagingProfile(null)
        } catch (error: unknown) {
            console.error('Failed to disconnect:', error)
            const errorMessage =
                (error as { data?: { error?: string } })?.data?.error ||
                t('composio.integrationsModal.toasts.failedToDisconnect', {
                    appName: managingProfile.toolkit_name
                })
            toast.error(
                t('composio.integrationsModal.toasts.failedToDisconnect', {
                    appName: managingProfile.toolkit_name
                }),
                {
                    description: errorMessage
                }
            )
        }
    }

    const renderContent = () => {
        if (isLoading) {
            return (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {Array.from({ length: 12 }).map((_, i) => (
                        <AppCardSkeleton key={i} />
                    ))}
                </div>
            )
        }

        if (filteredToolkits.length === 0) {
            return (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                    <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
                        <Icon name="search" className="size-8 fill-gray-400" />
                    </div>
                    <h3 className="text-lg font-medium text-gray-900 mb-2">
                        {t('composio.integrationsModal.noAppsFound')}
                    </h3>
                    <p className="text-gray-600">
                        {search
                            ? t(
                                  'composio.integrationsModal.noAppsMatchSearch',
                                  { search }
                              )
                            : t('composio.integrationsModal.noAppsAvailable')}
                    </p>
                </div>
            )
        }

        return (
            <div className="space-y-5">
                <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">
                        {search
                            ? t('composio.integrationsModal.searchResults', {
                                  count: filteredToolkits.length
                              })
                            : t('composio.integrationsModal.availableApps', {
                                  count: filteredToolkits.length
                              })}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {filteredToolkits.map((app) => (
                            <ComposioAppCard
                                key={app.slug}
                                app={app}
                                profiles={profilesByToolkit[app.slug] || []}
                                onConnect={() => handleConnect(app)}
                                onManage={(profile) =>
                                    setManagingProfile(profile)
                                }
                                isConnecting={connectingApp === app.slug}
                            />
                        ))}
                    </div>
                </div>
            </div>
        )
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                className="md:!max-w-[90vw] md:!w-[90vw] !h-[90vh] p-0 overflow-hidden flex flex-col !bg-white"
                aria-describedby="integrations-description"
            >
                {/* Header */}
                <DialogHeader className="px-3 md:px-10 pt-10 pb-8 border-b border-gray-100 shrink-0">
                    <DialogTitle className="text-3xl font-semibold tracking-tight text-gray-900">
                        {t('composio.integrationsModal.title')}
                    </DialogTitle>
                    <DialogDescription
                        id="integrations-description"
                        className="text-base text-gray-500 mt-2"
                    >
                        <Trans
                            i18nKey="composio.integrationsModal.description"
                            components={{
                                strong: <strong className="font-semibold" />
                            }}
                        />
                    </DialogDescription>
                </DialogHeader>

                {/* Search & Filters */}
                <div className="px-3 md:px-10 py-6 border-b border-gray-100 shrink-0">
                    <div className="space-y-4">
                        <div className="relative">
                            <Icon
                                name="search"
                                className="absolute left-3.5 top-1/2 transform -translate-y-1/2 w-4 h-4 stroke-black"
                                aria-hidden="true"
                            />
                            <Input
                                placeholder={t(
                                    'composio.integrationsModal.searchPlaceholder'
                                )}
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                aria-label={t(
                                    'composio.integrationsModal.searchLabel'
                                )}
                                className="pl-10 h-12 !text-black placeholder:text-black/50 !bg-black/10"
                            />
                            {search && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    aria-label={t(
                                        'composio.integrationsModal.clearSearch'
                                    )}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0 hover:bg-gray-100"
                                    onClick={() => setSearch('')}
                                >
                                    <Icon
                                        name="close"
                                        className="w-4 h-4 fill-gray-500"
                                    />
                                </Button>
                            )}
                        </div>

                        {/* Category Filters intentionally removed to simplify UI */}
                    </div>
                </div>

                {/* Content - Scrollable */}
                <div
                    className="flex-1 overflow-y-auto px-3 md:px-10 py-8 min-h-0 bg-white"
                    role="region"
                    aria-label={t(
                        'composio.integrationsModal.availableIntegrations'
                    )}
                >
                    {renderContent()}
                </div>
            </DialogContent>

            {managingProfile && (
                <ComposioManageModal
                    open={!!managingProfile}
                    onOpenChange={(open) => !open && setManagingProfile(null)}
                    profile={managingProfile}
                    onDisconnect={handleDisconnect}
                    toolkitsData={toolkits}
                />
            )}
        </Dialog>
    )
}

export default ComposioIntegrationsModal
