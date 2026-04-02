import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
    selectMessages,
    selectPublished,
    selectProjectId,
    useAppSelector
} from '@/state'
import { setPublished } from '@/state/slice/agent'
import { TOOL } from '@/typings'
import { Icon } from '../ui/icon'
import {
    subdomainService,
    CheckAvailabilityResponse,
    ClaimSubdomainResponse
} from '@/services/subdomain.service'
import { projectService } from '@/services/project.service'
import { ProjectDeploymentResponse } from '@/typings/project'
import { cn } from '@/lib/utils'
import { Loader2, Check, X } from 'lucide-react'

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value)

    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedValue(value)
        }, delay)

        return () => {
            clearTimeout(timer)
        }
    }, [value, delay])

    return debouncedValue
}

const ProjectDeployment = () => {
    const { t } = useTranslation()
    const dispatch = useDispatch()
    const messages = useSelector(selectMessages)
    const publishedUrl = useAppSelector(selectPublished)
    const projectId = useAppSelector(selectProjectId)

    // Subdomain state
    const [subdomain, setSubdomain] = useState('')
    const [isChecking, setIsChecking] = useState(false)
    const [availabilityResult, setAvailabilityResult] =
        useState<CheckAvailabilityResponse | null>(null)
    const [baseDomain, setBaseDomain] = useState('ii.inc')
    const [isSubmitting, setIsSubmitting] = useState(false)

    // Deployment state
    const [deploymentInfo, setDeploymentInfo] =
        useState<ProjectDeploymentResponse | null>(null)
    const [isLoadingDeployment, setIsLoadingDeployment] = useState(false)

    const debouncedSubdomain = useDebounce(subdomain.toLowerCase().trim(), 500)

    // Check if subdomain claiming is allowed
    const canClaimSubdomain =
        deploymentInfo?.has_deployment &&
        deploymentInfo?.provider === 'cloud_run'
    const isClaimingDisabled = !canClaimSubdomain

    // Fetch base domain info on mount
    useEffect(() => {
        const fetchBaseDomain = async () => {
            try {
                const info = await subdomainService.getBaseDomainInfo()
                setBaseDomain(info.base_domain)
            } catch {
                // Use default
            }
        }
        fetchBaseDomain()
    }, [])

    // Fetch deployment info when projectId changes
    useEffect(() => {
        const fetchDeploymentInfo = async () => {
            if (!projectId) {
                setDeploymentInfo(null)
                return
            }

            setIsLoadingDeployment(true)
            try {
                const info =
                    await projectService.getProjectDeployment(projectId)
                setDeploymentInfo(info)
            } catch {
                setDeploymentInfo(null)
            } finally {
                setIsLoadingDeployment(false)
            }
        }
        fetchDeploymentInfo()
    }, [projectId])

    // Check availability when debounced value changes
    useEffect(() => {
        const checkAvailability = async () => {
            if (!debouncedSubdomain || debouncedSubdomain.length < 2) {
                setAvailabilityResult(null)
                return
            }

            setIsChecking(true)
            try {
                const result =
                    await subdomainService.checkAvailability(debouncedSubdomain)
                setAvailabilityResult(result)
            } catch (error) {
                setAvailabilityResult({
                    subdomain: debouncedSubdomain,
                    available: false,
                    full_domain: null,
                    error: t('project.deployment.subdomain.checkError'),
                    suggestions: null
                })
            } finally {
                setIsChecking(false)
            }
        }

        checkAvailability()
    }, [debouncedSubdomain, t])

    const handleSubdomainChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            const value = e.target.value
                .toLowerCase()
                .replace(/[^a-z0-9-]/g, '')
            setSubdomain(value)
            setAvailabilityResult(null)
        },
        []
    )

    const handleSuggestionClick = useCallback((suggestion: string) => {
        // Extract subdomain from full domain (e.g., "myapp1.ii.inc" -> "myapp1")
        const parts = suggestion.split('.')
        if (parts.length > 0) {
            setSubdomain(parts[0])
        }
    }, [])

    const handleSubmitSubdomain = async () => {
        if (!availabilityResult?.available || !availabilityResult.full_domain) {
            return
        }

        if (!projectId) {
            toast.error(t('project.deployment.subdomain.noProjectError'))
            return
        }

        setIsSubmitting(true)
        try {
            const result: ClaimSubdomainResponse =
                await subdomainService.claimSubdomain(
                    projectId,
                    subdomain.toLowerCase().trim()
                )

            if (result.success) {
                toast.success(
                    t('project.deployment.subdomain.claimed', {
                        domain: result.full_domain
                    })
                )
                // Update the published URL state immediately
                if (result.production_url) {
                    dispatch(setPublished(result.production_url))
                }
                // Clear the input after successful claim
                setSubdomain('')
                setAvailabilityResult(null)
            } else {
                toast.error(
                    result.error || t('project.deployment.subdomain.claimError')
                )
            }
        } catch {
            toast.error(t('project.deployment.subdomain.claimError'))
        } finally {
            setIsSubmitting(false)
        }
    }

    const resultUrl = useMemo(() => {
        const fullstackResult = [...messages]
            .reverse()
            .find(
                (message) =>
                    message.action?.type === TOOL.FULLSTACK_PROJECT_INIT &&
                    message.action?.data?.result
            )

        const result = fullstackResult?.action?.data?.result
        if (result && typeof result === 'object') {
            const previewUrl = (result as { preview_url?: string }).preview_url
            if (previewUrl) {
                return previewUrl
            }
        }
        return ''
    }, [messages])

    const renderAvailabilityStatus = () => {
        if (isChecking) {
            return (
                <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('project.deployment.subdomain.checking')}
                </div>
            )
        }

        if (!availabilityResult) {
            return null
        }

        if (availabilityResult.available) {
            return (
                <div className="mt-2 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                    <Check className="h-4 w-4" />
                    {t('project.deployment.subdomain.available', {
                        domain: availabilityResult.full_domain
                    })}
                </div>
            )
        }

        return (
            <div className="mt-2 space-y-2">
                <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                    <X className="h-4 w-4" />
                    {availabilityResult.error ||
                        t('project.deployment.subdomain.taken')}
                </div>
                {availabilityResult.suggestions &&
                    availabilityResult.suggestions.length > 0 && (
                        <div className="space-y-1">
                            <p className="text-xs text-muted-foreground">
                                {t('project.deployment.subdomain.suggestions')}
                            </p>
                            <div className="flex flex-wrap gap-2">
                                {availabilityResult.suggestions.map(
                                    (suggestion) => (
                                        <button
                                            key={suggestion}
                                            onClick={() =>
                                                handleSuggestionClick(
                                                    suggestion
                                                )
                                            }
                                            className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                                        >
                                            {suggestion}
                                        </button>
                                    )
                                )}
                            </div>
                        </div>
                    )}
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="rounded-xl border border-white/60 bg-firefly/10 p-4 dark:border-white/10 dark:bg-sky-blue-2/10">
                <p className="text-base font-semibold text-firefly dark:text-sky-blue-2">
                    {t('project.deployment.iiDomainTitle')}
                </p>
                <p className="mt-1 text-sm text-muted-foreground dark:text-white">
                    {t('project.deployment.iiDomainDescription')}
                </p>
                <div className="mt-4 flex flex-col gap-3 md:flex-row">
                    <Input
                        readOnly
                        value={resultUrl || ''}
                        placeholder={t(
                            'project.deployment.noDeploymentPlaceholder'
                        )}
                        title={resultUrl || undefined}
                        className="bg-white/80 text-slate-900 dark:bg-sky-blue-2/10 dark:text-white text-sm overflow-hidden text-ellipsis whitespace-nowrap"
                    />
                    <Button
                        size="xl"
                        type="button"
                        variant="outline"
                        className="md:w-[160px] h-12 rounded-xl bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-charcoal"
                        disabled={!resultUrl}
                        onClick={() =>
                            resultUrl && window.open(resultUrl, '_blank')
                        }
                    >
                        <Icon
                            name="export"
                            className="fill-sky-blue-2 dark:fill-black"
                        />
                        {t('project.deployment.openUrl')}
                    </Button>
                </div>
            </div>

            <div className="rounded-xl border border-white/60 bg-firefly/10 p-4 dark:border-white/10 dark:bg-sky-blue-2/10">
                <p className="text-base font-semibold text-firefly dark:text-sky-blue-2">
                    {t('project.deployment.ownDomainTitle')}
                </p>
                <p className="mt-1 text-sm text-muted-foreground dark:text-white">
                    {t('project.deployment.subdomain.description')}
                </p>

                {/* Disabled message when claiming is not available */}
                {isLoadingDeployment && (
                    <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('project.deployment.subdomain.loadingDeployment')}
                    </div>
                )}

                {!isLoadingDeployment && isClaimingDisabled && (
                    <div className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                        {!deploymentInfo?.has_deployment
                            ? t('project.deployment.subdomain.noDeployment')
                            : t('project.deployment.subdomain.cloudRunOnly')}
                    </div>
                )}

                {/* Subdomain Input */}
                <div className="mt-4">
                    <div className="flex items-center gap-0">
                        <Input
                            value={subdomain}
                            onChange={handleSubdomainChange}
                            placeholder={t(
                                'project.deployment.subdomain.placeholder'
                            )}
                            disabled={isClaimingDisabled || isLoadingDeployment}
                            className={cn(
                                'rounded-r-none bg-white/80 text-slate-900 dark:bg-sky-blue-2/10 dark:text-white text-sm',
                                availabilityResult?.available &&
                                    !isClaimingDisabled &&
                                    'border-green-500 focus-visible:ring-green-500',
                                availabilityResult &&
                                    !availabilityResult.available &&
                                    !isClaimingDisabled &&
                                    'border-red-500 focus-visible:ring-red-500',
                                isClaimingDisabled &&
                                    'opacity-50 cursor-not-allowed'
                            )}
                        />
                        <div
                            className={cn(
                                'flex h-12 items-center rounded-r-xl border border-l-0 !border-black dark:!border-white bg-white/80 px-3 text-sm text-muted-foreground dark:bg-sky-blue-2/10',
                                isClaimingDisabled && 'opacity-50'
                            )}
                        >
                            .{baseDomain}
                        </div>
                    </div>
                    {!isClaimingDisabled && renderAvailabilityStatus()}
                </div>

                {/* Submit Button */}
                {availabilityResult?.available && !isClaimingDisabled && (
                    <div className="mt-4">
                        <Button
                            size="xl"
                            type="button"
                            className="h-12 rounded-xl bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-charcoal"
                            onClick={handleSubmitSubdomain}
                            disabled={isSubmitting}
                        >
                            {isSubmitting && (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            )}
                            {t('project.deployment.subdomain.claimDomain')}
                        </Button>
                    </div>
                )}

                {/* Show current published URL if exists */}
                {publishedUrl && (
                    <div className="mt-4 border-t border-white/20 pt-4">
                        <p className="mb-2 text-sm text-muted-foreground dark:text-white">
                            {t(
                                'project.deployment.ownDomainDescriptionConnected'
                            )}
                        </p>
                        <div className="flex flex-col gap-3 md:flex-row">
                            <Input
                                readOnly
                                value={publishedUrl || ''}
                                placeholder={t(
                                    'project.deployment.noDeploymentPlaceholder'
                                )}
                                title={publishedUrl || undefined}
                                className="bg-white/80 text-slate-900 dark:bg-sky-blue-2/10 dark:text-white text-sm overflow-hidden text-ellipsis whitespace-nowrap"
                            />
                            <Button
                                size="xl"
                                type="button"
                                variant="outline"
                                className="md:w-[160px] h-12 rounded-xl bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-charcoal"
                                disabled={!publishedUrl}
                                onClick={() =>
                                    publishedUrl &&
                                    window.open(publishedUrl, '_blank')
                                }
                            >
                                <Icon
                                    name="export"
                                    className="fill-sky-blue-2 dark:fill-black"
                                />
                                {t('project.deployment.openUrl')}
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

export default ProjectDeployment
