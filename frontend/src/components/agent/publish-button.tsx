'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle
} from '@/components/ui/dialog'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    selectLatestCheckpoint,
    selectPublished,
    setPublished,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { fullstackService } from '@/services/fullstack.service'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { Icon } from '../ui/icon'

type PublishProvider = 'cloud_run' | 'vercel'

interface PublishButtonProps {
    variant?: 'default' | 'outline' | 'ghost'
    size?: 'default' | 'sm' | 'lg' | 'icon'
    className?: string
    projectDirectory?: string
    revision?: string
}

export const PublishButton = ({
    variant = 'default',
    size = 'sm',
    className = '',
    projectDirectory: propProjectDirectory,
    revision: propRevision
}: PublishButtonProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const publishedUrl = useAppSelector(selectPublished)
    const latestCheckpoint = useAppSelector(selectLatestCheckpoint)
    const { sendMessage } = useSocketIOContext()
    const { sessionId } = useParams<{ sessionId: string }>()

    const [isPublishDialogOpen, setPublishDialogOpen] = useState(false)
    const [vercelApiKey, setVercelApiKey] = useState('')
    const [projectName, setProjectName] = useState('')
    const [isPublishing, setIsPublishing] = useState(false)
    const [_, setSelectedProvider] = useState<PublishProvider | null>(null)
    const lastPublishedUrlRef = useRef<string | null>(null)

    // Use props if provided, otherwise fall back to Redux state
    const projectDirectory =
        propProjectDirectory || latestCheckpoint?.projectDirectory
    const revision = propRevision || latestCheckpoint?.revision

    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    useEffect(() => {
        if (!publishedUrl || lastPublishedUrlRef.current === publishedUrl) {
            return
        }

        lastPublishedUrlRef.current = publishedUrl
        setIsPublishing(false)
        setPublishDialogOpen(false)
        setVercelApiKey('')
        setProjectName('')
        setSelectedProvider(null)
    }, [publishedUrl])

    useEffect(() => {
        if (
            !isPublishDialogOpen ||
            projectName ||
            !projectDirectory ||
            typeof projectDirectory !== 'string'
        ) {
            return
        }

        const fallback = projectDirectory.split('/').filter(Boolean).pop()

        if (fallback) {
            setProjectName(fallback)
        }
    }, [isPublishDialogOpen, projectDirectory, projectName])

    const handleOpenDeployment = () => {
        if (!publishedUrl) return
        window.open(publishedUrl, '_blank', 'noopener')
    }

    const handlePublishVercel = async () => {
        if (!projectDirectory || !revision) {
            toast.error(t('agent.publish.errors.checkpointMetadataMissing'))
            return
        }

        const trimmedKey = vercelApiKey.trim()
        if (!trimmedKey) {
            toast.error(t('agent.publish.errors.vercelApiKeyRequired'))
            return
        }

        try {
            setIsPublishing(true)
            setPublishDialogOpen(false)
            dispatch(setPublished(null))
            await fullstackService.publishProject({
                vercelApiKey: trimmedKey,
                sendMessage,
                sessionId: sessionId || '',
                projectName: projectName.trim() || undefined,
                projectPath: projectDirectory,
                revision
            })
            toast.success(t('agent.publish.toasts.requestSent'))
        } catch (error) {
            console.error('Failed to publish project', error)
            const fallbackMessage = t('agent.publish.errors.failedToPublish')
            const responseMessage =
                (
                    error as {
                        response?: {
                            data?: { detail?: string; message?: string }
                        }
                    }
                )?.response?.data?.detail ||
                (
                    error as {
                        response?: {
                            data?: { detail?: string; message?: string }
                        }
                    }
                )?.response?.data?.message ||
                (error as { message?: string }).message ||
                fallbackMessage

            toast.error(responseMessage)
            setIsPublishing(false)
            setPublishDialogOpen(true)
        }
    }

    const handlePublishCloudRun = async () => {
        if (!projectDirectory || !revision) {
            toast.error(t('agent.publish.errors.checkpointMetadataMissing'))
            return
        }

        try {
            setIsPublishing(true)
            dispatch(setPublished(null))
            await fullstackService.publishCloudRun({
                sendMessage,
                sessionId: sessionId || '',
                projectName: projectName.trim() || undefined,
                projectPath: projectDirectory,
                revision
            })
            toast.success(t('agent.publish.toasts.requestSent'))
        } catch (error) {
            console.error('Failed to publish to Cloud Run', error)
            const fallbackMessage = t('agent.publish.errors.failedToPublish')
            const responseMessage =
                (
                    error as {
                        response?: {
                            data?: { detail?: string; message?: string }
                        }
                    }
                )?.response?.data?.detail ||
                (
                    error as {
                        response?: {
                            data?: { detail?: string; message?: string }
                        }
                    }
                )?.response?.data?.message ||
                (error as { message?: string }).message ||
                fallbackMessage

            toast.error(responseMessage)
            setIsPublishing(false)
        }
    }

    const handleProviderSelect = (provider: PublishProvider) => {
        if (!projectDirectory || !revision) {
            toast.error(t('agent.publish.errors.noCheckpointAvailable'))
            return
        }

        setSelectedProvider(provider)

        if (provider === 'cloud_run') {
            // Cloud Run doesn't require API key, publish directly
            handlePublishCloudRun()
        } else {
            // Vercel requires API key, show dialog
            setPublishDialogOpen(true)
        }
    }

    const handleClick = () => {
        if (publishedUrl) {
            handleOpenDeployment()
        }
    }

    // Don't render anything in share mode
    if (isShareMode) {
        return null
    }

    return (
        <>
            {isPublishing ? (
                <Button
                    size={size}
                    variant={variant}
                    className={className}
                    disabled
                >
                    <Loader2 className="mr-2 size-3 animate-spin" />
                    {t('agent.publish.publishing')}
                </Button>
            ) : publishedUrl ? (
                <Button
                    size={size}
                    variant={variant}
                    className={className}
                    onClick={handleClick}
                    title={publishedUrl}
                >
                    {t('agent.publish.viewDeployment')}
                </Button>
            ) : (
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            disabled={!projectDirectory || !revision}
                            size={size}
                            variant={variant}
                            className={className}
                        >
                            {t('agent.publish.publish')}
                            <Icon
                                name="arrow-down"
                                className="size-4 fill-black"
                            />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem
                            onClick={() => handleProviderSelect('cloud_run')}
                        >
                            Cloud Run
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => handleProviderSelect('vercel')}
                        >
                            Vercel
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            )}

            <Dialog
                open={isPublishDialogOpen}
                onOpenChange={setPublishDialogOpen}
            >
                <DialogContent
                    className="!bg-white text-black rounded-2xl border border-grey/70 dark:border-sky-blue-2/30 shadow-btn backdrop-blur-xl p-6 md:p-8"
                    showCloseButton={!isPublishing}
                >
                    <DialogHeader className="gap-1">
                        <DialogTitle className="text-2xl font-semibold text-black">
                            {t('agent.publish.dialog.title')}
                        </DialogTitle>
                        <DialogDescription className="text-sm text-black">
                            {t('agent.publish.dialog.description')}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label
                                htmlFor="vercel-api-key"
                                className="text-sm font-medium text-black"
                            >
                                {t('agent.publish.form.vercelApiKeyLabel')}
                            </Label>
                            <Input
                                id="vercel-api-key"
                                type="password"
                                value={vercelApiKey}
                                onChange={(event) =>
                                    setVercelApiKey(event.target.value)
                                }
                                placeholder={t(
                                    'agent.publish.form.vercelApiKeyPlaceholder'
                                )}
                                className="!text-black placeholder:text-black/50 !bg-black/10"
                            />
                        </div>
                    </div>
                    <DialogFooter className="sm:justify-end gap-3">
                        <Button
                            variant="outline"
                            onClick={() => setPublishDialogOpen(false)}
                            disabled={isPublishing}
                            className="text-black"
                        >
                            {t('common.cancel')}
                        </Button>
                        <Button
                            onClick={handlePublishVercel}
                            disabled={isPublishing || !vercelApiKey.trim()}
                            className="bg-sky-blue text-black"
                        >
                            {isPublishing ? (
                                <span className="flex items-center gap-2">
                                    <Loader2 className="size-4 animate-spin" />
                                    {t('agent.publish.publishing')}
                                </span>
                            ) : (
                                t('agent.publish.publish')
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    )
}
