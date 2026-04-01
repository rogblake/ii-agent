'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router'
import { Loader2, CheckCircle2, ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Icon } from '@/components/ui/icon'
import { cn } from '@/lib/utils'
import { AgentEvent, CommandType, type ChatMessagePayload } from '@/typings/agent'
import { useSocketIOContext } from '@/contexts/websocket-context'

// Types
interface AppleTeam {
    team_id: string
    name: string
    team_type: string
}

interface AppleApp {
    app_id: string
    name: string
    bundle_id: string
    sku: string
    icon_url?: string
}

type WizardStep =
    | 'expo'
    | 'apple_login'
    | '2fa'
    | 'team_selection'
    | 'app_setup'
    | 'building'

interface TestflightWizardDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
}

const DIALOG_INPUT_CLASS_NAME =
    'text-black placeholder:text-black/50 bg-black/10 dark:bg-black/10 dark:text-black dark:placeholder:text-black/50'

const STEPS: { key: WizardStep; labelKey: string }[] = [
    { key: 'expo', labelKey: 'agent.mobilePublish.testflightWizard.steps.expo' },
    {
        key: 'apple_login',
        labelKey: 'agent.mobilePublish.testflightWizard.steps.appleLogin'
    },
    {
        key: '2fa',
        labelKey: 'agent.mobilePublish.testflightWizard.steps.verification'
    },
    {
        key: 'team_selection',
        labelKey: 'agent.mobilePublish.testflightWizard.steps.teamSelection'
    },
    {
        key: 'app_setup',
        labelKey: 'agent.mobilePublish.testflightWizard.steps.appSetup'
    },
    {
        key: 'building',
        labelKey: 'agent.mobilePublish.testflightWizard.steps.build'
    }
]

export const TestflightWizardDialog = ({
    open,
    onOpenChange
}: TestflightWizardDialogProps) => {
    const { t } = useTranslation()
    const { socket, sendMessage } = useSocketIOContext()
    const { sessionId } = useParams<{ sessionId: string }>()
    const [currentStep, setCurrentStep] = useState<WizardStep>('expo')
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    // Form data
    const [expoToken, setExpoToken] = useState('')
    const [appleId, setAppleId] = useState('')
    const [password, setPassword] = useState('')
    const [twoFactorCode, setTwoFactorCode] = useState('')
    const [teams, setTeams] = useState<AppleTeam[]>([])
    const [selectedTeam, setSelectedTeam] = useState<AppleTeam | null>(null)
    const [bundleId, setBundleId] = useState('')
    const [appName, setAppName] = useState('')

    // Build progress
    const [buildLogs, setBuildLogs] = useState<string[]>([])
    const [buildStatus, setBuildStatus] = useState<
        'idle' | 'running' | 'completed' | 'failed'
    >('idle')

    // Existing apps
    const [existingApps, setExistingApps] = useState<AppleApp[]>([])
    const [showExistingApps, setShowExistingApps] = useState(false)
    const [selectedExistingApp, setSelectedExistingApp] =
        useState<AppleApp | null>(null)
    const [loadingApps, setLoadingApps] = useState(false)

    // App setup progress
    const [setupStep, setSetupStep] = useState<number>(0)
    const [setupTotalSteps, setSetupTotalSteps] = useState<number>(3)
    const [setupMessage, setSetupMessage] = useState<string>('')
    const [ascAppId, setAscAppId] = useState<string>('')

    // Existing auth state
    const [hasExistingAuth, setHasExistingAuth] = useState(false)
    const [existingAuthAppleId, setExistingAuthAppleId] = useState<
        string | null
    >(null)
    const [existingAuthTeamName, setExistingAuthTeamName] = useState<
        string | null
    >(null)
    const [checkingAuth, setCheckingAuth] = useState(false)
    const [hasStoredExpoToken, setHasStoredExpoToken] = useState(false)

    // App-Specific Password for auto-submit
    const [appSpecificPassword, setAppSpecificPassword] = useState('')
    const [hasStoredAppSpecificPassword, setHasStoredAppSpecificPassword] =
        useState(false)

    // Define handleStartBuild before the effect that uses it
    const handleStartBuild = useCallback(
        (appId?: string) => {
            setCurrentStep('building')
            setBuildStatus('running')
            setBuildLogs([])

            // Use provided appId, or fallback to state, or selected existing app
            const effectiveAscAppId =
                appId || ascAppId || selectedExistingApp?.app_id || ''

            // Build content with app-specific password if provided
            const content: Record<string, string> = {
                expo_token: expoToken.trim(),
                bundle_identifier: bundleId.trim(),
                asc_app_id: effectiveAscAppId
            }

            // Include app-specific password if user entered one (will be saved to DB)
            if (appSpecificPassword.trim()) {
                content.app_specific_password = appSpecificPassword.trim()
            }

            const success = sendMessage({
                session_uuid: sessionId || '',
                content: {
                    command: CommandType.SUBMIT_TESTFLIGHT,
                    ...content
                } as ChatMessagePayload['content']
            })

            if (!success) {
                setBuildStatus('failed')
                toast.error(
                    t('agent.mobilePublish.testflightWizard.toasts.startFailed')
                )
            }
        },
        [
            expoToken,
            bundleId,
            ascAppId,
            selectedExistingApp,
            appSpecificPassword,
            sendMessage,
            t
        ]
    )

    // Handle socket events directly from the socket
    useEffect(() => {
        if (!open || !socket) return

        const handleChatEvent = (data: {
            type: string
            content: Record<string, unknown>
        }) => {
            const { type, content } = data

            switch (type) {
                case AgentEvent.APPLE_AUTH_CHECK_RESULT:
                    setCheckingAuth(false)
                    // Pre-fill expo token if available
                    if (content.expo_token) {
                        setExpoToken(content.expo_token as string)
                        setHasStoredExpoToken(true)
                    }
                    // Pre-fill app-specific password status
                    if (content.has_app_specific_password) {
                        setHasStoredAppSpecificPassword(true)
                    }
                    // Pre-fill apple_id if available (for convenience)
                    if (content.apple_id) {
                        setAppleId(content.apple_id as string)
                    }
                    // Store team info for display but always require re-auth
                    if (content.team_name) {
                        setExistingAuthTeamName(content.team_name as string)
                    }
                    // Never skip auth - always require login for security
                    setHasExistingAuth(false)
                    break

                case AgentEvent.APPLE_AUTH_STATUS:
                    // Handle different auth statuses
                    // Only set isLoading to false for terminal states
                    if (content.status === 'authenticated') {
                        setIsLoading(false)
                        toast.success(content.message as string)
                        setCurrentStep('app_setup')
                    } else if (
                        content.status === 'authenticating' ||
                        content.status === 'verifying'
                    ) {
                        // Keep loading for in-progress states
                        setIsLoading(true)
                    } else if (content.status === 'error') {
                        // Only stop loading on explicit error
                        setIsLoading(false)
                    }
                    // Don't change loading state for other/unknown statuses
                    break

                case AgentEvent.APPLE_2FA_REQUIRED:
                    // Stop loading and show 2FA step
                    setIsLoading(false)
                    setCurrentStep('2fa')
                    break

                case AgentEvent.APPLE_TEAM_SELECTION:
                    // Stop loading and show team selection
                    setIsLoading(false)
                    if (content.teams) {
                        setTeams(content.teams as AppleTeam[])
                    }
                    setCurrentStep('team_selection')
                    break

                case AgentEvent.APPLE_APP_SETUP_STATUS:
                    // Update setup progress
                    if (content.step) {
                        setSetupStep(content.step as number)
                    }
                    if (content.total_steps) {
                        setSetupTotalSteps(content.total_steps as number)
                    }
                    if (content.message) {
                        setSetupMessage(content.message as string)
                    }

                    if (content.status === 'completed') {
                        setIsLoading(false)
                        toast.success(content.message as string)
                        // Capture the App Store Connect app ID from the setup result
                        const completedAppId = content.app_id as string
                        if (completedAppId) {
                            setAscAppId(completedAppId)
                        }
                        // Start the build directly, passing the app ID
                        handleStartBuild(completedAppId)
                    } else if (content.warning) {
                        toast.warning(content.message as string)
                    } else if (
                        content.status === 'registering_bundle' ||
                        content.status === 'creating_certificate' ||
                        content.status === 'finalizing'
                    ) {
                        // Keep loading state during setup steps
                        setIsLoading(true)
                    }
                    break

                case AgentEvent.APPLE_APPS_LIST:
                    setLoadingApps(false)
                    if (content.apps) {
                        setExistingApps(content.apps as AppleApp[])
                        setShowExistingApps(true)
                    }
                    break

                case AgentEvent.TESTFLIGHT_LOG:
                    if (content.message) {
                        setBuildLogs((prev) => [
                            ...prev,
                            content.message as string
                        ])
                    }
                    if (content.status === 'completed') {
                        setBuildStatus('completed')
                        toast.success(
                            t(
                                'agent.mobilePublish.testflightWizard.toasts.submissionCompleted'
                            )
                        )
                    } else if (content.status === 'failed') {
                        setBuildStatus('failed')
                        toast.error(content.message as string)
                    }
                    break

                case AgentEvent.EXPO_TOKEN_SAVED:
                    // Token saved successfully, no need to show a toast
                    setHasStoredExpoToken(true)
                    break

                case AgentEvent.ERROR:
                    setIsLoading(false)
                    setError(content.message as string)
                    toast.error(content.message as string)

                    // If session expired, reset auth state and go back to login
                    if (content.error_type === 'session_expired') {
                        setHasExistingAuth(false)
                        setExistingAuthAppleId(null)
                        setExistingAuthTeamName(null)
                        setPassword('')
                        // If we're past the login step, go back to it
                        if (
                            currentStep !== 'expo' &&
                            currentStep !== 'apple_login'
                        ) {
                            setCurrentStep('apple_login')
                            toast.warning(
                                t(
                                    'agent.mobilePublish.testflightWizard.toasts.sessionExpired'
                                )
                            )
                        }
                    }

                    // If app name is taken, stay on app_setup step to let user change name
                    if (content.error_type === 'name_taken') {
                        setCurrentStep('app_setup')
                        toast.warning(
                            t(
                                'agent.mobilePublish.testflightWizard.toasts.nameTaken'
                            )
                        )
                    }

                    // If bundle ID is taken, stay on app_setup step to let user change bundle ID
                    if (content.error_type === 'bundle_id_taken') {
                        setCurrentStep('app_setup')
                        toast.warning(
                            t(
                                'agent.mobilePublish.testflightWizard.toasts.bundleIdTaken'
                            )
                        )
                    }
                    break
            }
        }

        socket.on('chat_event', handleChatEvent)

        return () => {
            socket.off('chat_event', handleChatEvent)
        }
    }, [socket, open, handleStartBuild, currentStep])

    // Reset state when dialog opens and check for existing auth
    useEffect(() => {
        if (open) {
            setCurrentStep('expo')
            setIsLoading(false)
            setError(null)
            setBuildLogs([])
            setBuildStatus('idle')
            setSetupStep(0)
            setSetupTotalSteps(4)
            setSetupMessage('')
            setAscAppId('')
            setExistingApps([])
            setShowExistingApps(false)
            setSelectedExistingApp(null)
            setLoadingApps(false)
            setHasExistingAuth(false)
            setExistingAuthAppleId(null)
            setExistingAuthTeamName(null)
            setCheckingAuth(true)
            setHasStoredExpoToken(false)
            setHasStoredAppSpecificPassword(false)
            setAppSpecificPassword('')

            // Check for existing Apple auth
            sendMessage({
                session_uuid: sessionId || '',
                content: { command: CommandType.APPLE_CHECK_AUTH }
            })
        }
    }, [open, sendMessage])

    const handleExpoSubmit = () => {
        if (!expoToken.trim()) {
            toast.error(
                t('agent.mobilePublish.testflightWizard.toasts.expoTokenRequired')
            )
            return
        }
        // Save the expo token if it's new or changed
        if (!hasStoredExpoToken) {
            sendMessage({
                session_uuid: sessionId || '',
                content: {
                    command: CommandType.SAVE_EXPO_TOKEN,
                    expo_token: expoToken.trim()
                } as ChatMessagePayload['content']
            })
        }
        // Always require Apple login for security (don't store passwords)
        setCurrentStep('apple_login')
    }

    const handleAppleLogin = async () => {
        if (!appleId.trim() || !password.trim()) {
            toast.error(
                t(
                    'agent.mobilePublish.testflightWizard.toasts.appleIdPasswordRequired'
                )
            )
            return
        }

        setIsLoading(true)
        setError(null)

        const success = sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.APPLE_AUTH_LOGIN,
                apple_id: appleId.trim(),
                password: password.trim()
            } as ChatMessagePayload['content']
        })

        if (!success) {
            setIsLoading(false)
            toast.error(
                t(
                    'agent.mobilePublish.testflightWizard.toasts.loginRequestFailed'
                )
            )
        }
    }

    const handle2FASubmit = async () => {
        if (!twoFactorCode.trim() || twoFactorCode.length !== 6) {
            toast.error(
                t(
                    'agent.mobilePublish.testflightWizard.toasts.invalidTwoFactor'
                )
            )
            return
        }

        setIsLoading(true)
        setError(null)

        const success = sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.APPLE_AUTH_2FA,
                code: twoFactorCode.trim()
            } as ChatMessagePayload['content']
        })

        if (!success) {
            setIsLoading(false)
            toast.error(
                t(
                    'agent.mobilePublish.testflightWizard.toasts.verificationFailed'
                )
            )
        }
    }

    const handleTeamSelect = async (team: AppleTeam) => {
        setSelectedTeam(team)
        setIsLoading(true)
        setError(null)

        const success = sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.APPLE_AUTH_SELECT_TEAM,
                team_id: team.team_id
            } as ChatMessagePayload['content']
        })

        if (!success) {
            setIsLoading(false)
            toast.error(
                t('agent.mobilePublish.testflightWizard.toasts.selectTeamFailed')
            )
        }
    }

    const handleFetchExistingApps = () => {
        setLoadingApps(true)
        setError(null)

        const success = sendMessage({
            session_uuid: sessionId || '',
            content: { command: CommandType.APPLE_LIST_APPS }
        })

        if (!success) {
            setLoadingApps(false)
            toast.error(
                t('agent.mobilePublish.testflightWizard.toasts.fetchAppsFailed')
            )
        }
    }

    const handleSelectExistingApp = (app: AppleApp) => {
        setSelectedExistingApp(app)
        setBundleId(app.bundle_id)
        setAppName(app.name)
        setShowExistingApps(false)
    }

    const handleAppSetup = async () => {
        if (!bundleId.trim() || !appName.trim()) {
            toast.error(
                t(
                    'agent.mobilePublish.testflightWizard.toasts.bundleAndNameRequired'
                )
            )
            return
        }

        // Only require password if user went through login flow (not using existing auth)
        // When using existing auth, the password is already stored in the database
        if (!hasExistingAuth && !password.trim()) {
            toast.error(
                t(
                    'agent.mobilePublish.testflightWizard.toasts.passwordRequired'
                )
            )
            return
        }

        setIsLoading(true)
        setError(null)

        // Build content - only include password if not using existing auth
        const content: Record<string, string> = {
            bundle_identifier: bundleId.trim(),
            app_name: appName.trim()
        }

        // Only include password if user entered it (not using existing auth)
        if (!hasExistingAuth && password.trim()) {
            content.password = password.trim()
        }

        const success = sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.APPLE_APP_SETUP,
                ...content
            } as ChatMessagePayload['content']
        })

        if (!success) {
            setIsLoading(false)
            toast.error(
                t('agent.mobilePublish.testflightWizard.toasts.setupFailed')
            )
        }
    }

    const getStepIndex = (step: WizardStep) => {
        return STEPS.findIndex((s) => s.key === step)
    }

    const currentStepIndex = getStepIndex(currentStep)

    const canGoBack = currentStepIndex > 0 && currentStep !== 'building'

    const handleBack = () => {
        if (currentStep === 'apple_login') {
            setCurrentStep('expo')
        } else if (currentStep === '2fa') {
            setCurrentStep('apple_login')
            setTwoFactorCode('')
        } else if (currentStep === 'team_selection') {
            setCurrentStep('apple_login')
        } else if (currentStep === 'app_setup') {
            setCurrentStep('team_selection')
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="!bg-white text-black rounded-2xl border border-grey/70 dark:border-sky-blue-2/30 shadow-btn backdrop-blur-xl p-6 md:p-8 max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader className="gap-1">
                    <DialogTitle className="text-2xl font-semibold text-black flex items-center gap-2">
                        {canGoBack && (
                            <button
                                onClick={handleBack}
                                className="p-1 hover:bg-gray-100 rounded-full"
                            >
                                <ArrowLeft className="w-5 h-5" />
                            </button>
                        )}
                        {t('agent.mobilePublish.testflightWizard.title')}
                    </DialogTitle>
                    <DialogDescription className="text-sm text-black">
                        {t('agent.mobilePublish.testflightWizard.description')}
                    </DialogDescription>
                </DialogHeader>

                {/* Step Indicator */}
                <div className="flex items-center justify-between mt-4 mb-6">
                    {STEPS.map((step, index) => (
                        <div
                            key={step.key}
                            className="flex items-center"
                            aria-label={t(step.labelKey)}
                        >
                            <div
                                className={cn(
                                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium',
                                    index < currentStepIndex
                                        ? 'bg-green-500 text-white'
                                        : index === currentStepIndex
                                          ? 'bg-blue-500 text-white'
                                          : 'bg-gray-200 text-gray-500'
                                )}
                            >
                                {index < currentStepIndex ? (
                                    <CheckCircle2 className="w-5 h-5" />
                                ) : (
                                    index + 1
                                )}
                            </div>
                            {index < STEPS.length - 1 && (
                                <div
                                    className={cn(
                                        'w-8 h-0.5 mx-1',
                                        index < currentStepIndex
                                            ? 'bg-green-500'
                                            : 'bg-gray-200'
                                    )}
                                />
                            )}
                        </div>
                    ))}
                </div>

                {/* Step Content */}
                <div className="space-y-5">
                    {/* Step 1: Expo Setup */}
                    {currentStep === 'expo' && (
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label
                                    htmlFor="expoToken"
                                    className="text-sm font-medium text-black"
                                >
                                    {t(
                                        'agent.mobilePublish.testflightWizard.expo.tokenLabel'
                                    )}{' '}
                                    <span className="text-red-500">*</span>
                                </Label>
                                {hasStoredExpoToken ? (
                                    <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                                        <CheckCircle2 className="w-4 h-4 text-green-600" />
                                        <span className="text-sm text-green-800">
                                            {t(
                                                'agent.mobilePublish.testflightWizard.expo.tokenSaved'
                                            )}
                                        </span>
                                        <button
                                            onClick={() => {
                                                setHasStoredExpoToken(false)
                                                setExpoToken('')
                                            }}
                                            className="ml-auto text-xs text-blue-600 hover:underline"
                                        >
                                            {t(
                                                'agent.mobilePublish.testflightWizard.expo.change'
                                            )}
                                        </button>
                                    </div>
                                ) : (
                                    <>
                                        <Input
                                            id="expoToken"
                                            type="password"
                                            placeholder={t(
                                                'agent.mobilePublish.testflightWizard.expo.tokenPlaceholder'
                                            )}
                                            value={expoToken}
                                            onChange={(e) =>
                                                setExpoToken(e.target.value)
                                            }
                                            className={DIALOG_INPUT_CLASS_NAME}
                                        />
                                        <p className="text-xs text-gray-500">
                                            <a
                                                href="https://expo.dev/settings/access-tokens"
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-blue-600 hover:underline"
                                            >
                                                {t(
                                                    'agent.mobilePublish.testflightWizard.expo.getToken'
                                                )}
                                            </a>
                                        </p>
                                    </>
                                )}
                            </div>
                            {/* Show existing auth status */}
                            {checkingAuth ? (
                                <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
                                    <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
                                    <span className="text-sm text-gray-600">
                                        {t(
                                            'agent.mobilePublish.testflightWizard.expo.checkingAuth'
                                        )}
                                    </span>
                                </div>
                            ) : hasExistingAuth ? (
                                <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                                    <CheckCircle2 className="w-4 h-4 text-green-600" />
                                    <span className="text-sm text-green-800">
                                        {existingAuthTeamName
                                            ? t(
                                                  'agent.mobilePublish.testflightWizard.expo.alreadySignedInWithTeam',
                                                  {
                                                      appleId:
                                                          existingAuthAppleId,
                                                      teamName:
                                                          existingAuthTeamName
                                                  }
                                              )
                                            : t(
                                                  'agent.mobilePublish.testflightWizard.expo.alreadySignedIn',
                                                  {
                                                      appleId:
                                                          existingAuthAppleId
                                                  }
                                              )}
                                    </span>
                                </div>
                            ) : null}
                            <Button
                                onClick={handleExpoSubmit}
                                disabled={
                                    checkingAuth ||
                                    (!hasStoredExpoToken && !expoToken.trim())
                                }
                                className="w-full bg-sky-blue text-black"
                            >
                                {hasExistingAuth && hasStoredExpoToken
                                    ? t(
                                          'agent.mobilePublish.testflightWizard.expo.continueToAppSetup'
                                      )
                                    : hasExistingAuth
                                      ? t(
                                            'agent.mobilePublish.testflightWizard.expo.saveAndContinueToAppSetup'
                                        )
                                      : t(
                                            'agent.mobilePublish.testflightWizard.expo.continue'
                                        )}
                            </Button>
                        </div>
                    )}

                    {/* Step 2: Apple Login */}
                    {currentStep === 'apple_login' && (
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label
                                    htmlFor="appleId"
                                    className="text-sm font-medium text-black"
                                >
                                    {t(
                                        'agent.mobilePublish.testflightWizard.appleLogin.appleIdLabel'
                                    )}{' '}
                                    <span className="text-red-500">*</span>
                                </Label>
                                <Input
                                    id="appleId"
                                    type="email"
                                    placeholder={t(
                                        'agent.mobilePublish.testflightWizard.appleLogin.appleIdPlaceholder'
                                    )}
                                    value={appleId}
                                    onChange={(e) => setAppleId(e.target.value)}
                                    className={DIALOG_INPUT_CLASS_NAME}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label
                                    htmlFor="password"
                                    className="text-sm font-medium text-black"
                                >
                                    {t(
                                        'agent.mobilePublish.testflightWizard.appleLogin.passwordLabel'
                                    )}{' '}
                                    <span className="text-red-500">*</span>
                                </Label>
                                <Input
                                    id="password"
                                    type="password"
                                    placeholder={t(
                                        'agent.mobilePublish.testflightWizard.appleLogin.passwordPlaceholder'
                                    )}
                                    value={password}
                                    onChange={(e) =>
                                        setPassword(e.target.value)
                                    }
                                    className={DIALOG_INPUT_CLASS_NAME}
                                />
                            </div>
                            <div className="flex items-start gap-3 p-4 bg-blue-50 border border-blue-200 rounded-xl">
                                <Icon
                                    name="info-circle"
                                    className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
                                />
                                <div className="text-sm text-blue-800">
                                    <p>
                                        {t(
                                            'agent.mobilePublish.testflightWizard.appleLogin.info'
                                        )}
                                    </p>
                                </div>
                            </div>
                            <Button
                                onClick={handleAppleLogin}
                                disabled={isLoading}
                                className="w-full bg-sky-blue text-black"
                            >
                                {isLoading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        {t(
                                            'agent.mobilePublish.testflightWizard.appleLogin.signingIn'
                                        )}
                                    </>
                                ) : (
                                    t(
                                        'agent.mobilePublish.testflightWizard.appleLogin.signIn'
                                    )
                                )}
                            </Button>
                        </div>
                    )}

                    {/* Step 3: 2FA */}
                    {currentStep === '2fa' && (
                        <div className="space-y-4">
                            <div className="text-center mb-4">
                                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <Icon
                                        name="shield"
                                        className="w-8 h-8 text-blue-600"
                                    />
                                </div>
                                <h3 className="text-lg font-medium text-black">
                                    {t(
                                        'agent.mobilePublish.testflightWizard.twoFactor.title'
                                    )}
                                </h3>
                                <p className="text-sm text-gray-600 mt-1">
                                    {t(
                                        'agent.mobilePublish.testflightWizard.twoFactor.description'
                                    )}
                                </p>
                            </div>
                            <div className="space-y-2">
                                <Input
                                    id="twoFactorCode"
                                    type="text"
                                    placeholder={t(
                                        'agent.mobilePublish.testflightWizard.twoFactor.placeholder'
                                    )}
                                    value={twoFactorCode}
                                    onChange={(e) =>
                                        setTwoFactorCode(
                                            e.target.value
                                                .replace(/\D/g, '')
                                                .slice(0, 6)
                                        )
                                    }
                                    className={`${DIALOG_INPUT_CLASS_NAME} text-center text-2xl tracking-widest`}
                                    maxLength={6}
                                />
                            </div>
                            <Button
                                onClick={handle2FASubmit}
                                disabled={
                                    isLoading || twoFactorCode.length !== 6
                                }
                                className="w-full bg-sky-blue text-black"
                            >
                                {isLoading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        {t(
                                            'agent.mobilePublish.testflightWizard.twoFactor.verifying'
                                        )}
                                    </>
                                ) : (
                                    t(
                                        'agent.mobilePublish.testflightWizard.twoFactor.verify'
                                    )
                                )}
                            </Button>
                        </div>
                    )}

                    {/* Step 4: Team Selection */}
                    {currentStep === 'team_selection' && (
                        <div className="space-y-4">
                            <p className="text-sm text-gray-600">
                                {t(
                                    'agent.mobilePublish.testflightWizard.teamSelection.prompt'
                                )}
                            </p>
                            <div className="space-y-2">
                                {teams.map((team) => (
                                    <button
                                        key={team.team_id}
                                        onClick={() => handleTeamSelect(team)}
                                        disabled={isLoading}
                                        className={cn(
                                            'w-full p-4 rounded-xl border text-left transition-all',
                                            selectedTeam?.team_id ===
                                                team.team_id
                                                ? 'border-blue-500 bg-blue-50'
                                                : 'border-gray-200 hover:border-gray-300 bg-white'
                                        )}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <p className="font-medium text-black">
                                                    {team.name}
                                                </p>
                                                <p className="text-xs text-gray-500 mt-1">
                                                    {team.team_type} &bull;{' '}
                                                    {team.team_id}
                                                </p>
                                            </div>
                                            {selectedTeam?.team_id ===
                                                team.team_id &&
                                                isLoading && (
                                                    <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                                                )}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Step 5: App Setup */}
                    {currentStep === 'app_setup' && (
                        <div className="space-y-4">
                            {/* Show progress when setting up */}
                            {isLoading && setupMessage ? (
                                <div className="space-y-4">
                                    <div className="flex items-center gap-3">
                                        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                                        <div>
                                            <h3 className="font-medium text-black">
                                                {t(
                                                    'agent.mobilePublish.testflightWizard.appSetup.title'
                                                )}
                                            </h3>
                                            <p className="text-sm text-gray-500">
                                                {t(
                                                    'agent.mobilePublish.testflightWizard.appSetup.stepOf',
                                                    {
                                                        current: setupStep,
                                                        total: setupTotalSteps
                                                    }
                                                )}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="bg-gray-100 rounded-xl p-4">
                                        <p className="text-sm text-gray-700">
                                            {setupMessage}
                                        </p>
                                    </div>
                                    {/* Progress bar */}
                                    <div className="w-full bg-gray-200 rounded-full h-2">
                                        <div
                                            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                                            style={{
                                                width: `${(setupStep / setupTotalSteps) * 100}%`
                                            }}
                                        />
                                    </div>
                                </div>
                            ) : showExistingApps ? (
                                // Show existing apps list
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between">
                                        <h3 className="font-medium text-black">
                                            {t(
                                                'agent.mobilePublish.testflightWizard.appSetup.selectExisting'
                                            )}
                                        </h3>
                                        <button
                                            onClick={() =>
                                                setShowExistingApps(false)
                                            }
                                            className="cursor-pointer text-sm text-blue-600 hover:underline"
                                        >
                                            {t(
                                                'agent.mobilePublish.testflightWizard.appSetup.createNew'
                                            )}
                                        </button>
                                    </div>
                                    {existingApps.length === 0 ? (
                                        <div className="text-center py-8 text-gray-500">
                                            <p>
                                                {t(
                                                    'agent.mobilePublish.testflightWizard.appSetup.noApps'
                                                )}
                                            </p>
                                            <button
                                                onClick={() =>
                                                    setShowExistingApps(false)
                                                }
                                                className="mt-2 text-blue-600 hover:underline"
                                            >
                                                {t(
                                                    'agent.mobilePublish.testflightWizard.appSetup.createInstead'
                                                )}
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="space-y-2 max-h-64 overflow-y-auto">
                                            {existingApps.map((app) => (
                                                <button
                                                    key={app.app_id}
                                                    onClick={() =>
                                                        handleSelectExistingApp(
                                                            app
                                                        )
                                                    }
                                                    className={cn(
                                                        'cursor-pointer w-full p-4 rounded-xl border text-left transition-all',
                                                        selectedExistingApp?.app_id ===
                                                            app.app_id
                                                            ? 'border-blue-500 bg-blue-50'
                                                            : 'border-gray-200 hover:border-gray-300 bg-white'
                                                    )}
                                                >
                                                    <p className="font-medium text-black truncate">
                                                        {app.name}
                                                    </p>
                                                    <p className="text-xs text-gray-500 mt-0.5 truncate">
                                                        {app.bundle_id}
                                                    </p>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ) : (
                                // Show new app form
                                <>
                                    {/* Use existing app button */}
                                    <div className="flex justify-end">
                                        <button
                                            onClick={handleFetchExistingApps}
                                            disabled={loadingApps}
                                            className="cursor-pointer text-sm text-blue-600 hover:underline flex items-center gap-1"
                                        >
                                            {loadingApps ? (
                                                <>
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                    {t(
                                                        'agent.mobilePublish.testflightWizard.appSetup.loadingApps'
                                                    )}
                                                </>
                                            ) : (
                                                t(
                                                    'agent.mobilePublish.testflightWizard.appSetup.useExisting'
                                                )
                                            )}
                                        </button>
                                    </div>
                                    <div className="space-y-2">
                                        <Label
                                            htmlFor="bundleId"
                                            className="text-sm font-medium text-black"
                                        >
                                            {t(
                                                'agent.mobilePublish.testflightWizard.appSetup.bundleIdLabel'
                                            )}{' '}
                                            <span className="text-red-500">
                                                *
                                            </span>
                                        </Label>
                                        <Input
                                            id="bundleId"
                                            type="text"
                                            placeholder={t(
                                                'agent.mobilePublish.testflightWizard.appSetup.bundleIdPlaceholder'
                                            )}
                                            value={bundleId}
                                            onChange={(e) =>
                                                setBundleId(e.target.value)
                                            }
                                            className={DIALOG_INPUT_CLASS_NAME}
                                        />
                                        <p className="text-xs text-gray-500">
                                            {t(
                                                'agent.mobilePublish.testflightWizard.appSetup.bundleIdHelp'
                                            )}
                                        </p>
                                    </div>
                                    <div className="space-y-2">
                                        <Label
                                            htmlFor="appName"
                                            className="text-sm font-medium text-black"
                                        >
                                            {t(
                                                'agent.mobilePublish.testflightWizard.appSetup.appNameLabel'
                                            )}{' '}
                                            <span className="text-red-500">
                                                *
                                            </span>
                                        </Label>
                                        <Input
                                            id="appName"
                                            type="text"
                                            placeholder={t(
                                                'agent.mobilePublish.testflightWizard.appSetup.appNamePlaceholder'
                                            )}
                                            value={appName}
                                            onChange={(e) =>
                                                setAppName(e.target.value)
                                            }
                                            className={DIALOG_INPUT_CLASS_NAME}
                                        />
                                    </div>
                                    {/* App-Specific Password for auto-submit */}
                                    <div className="space-y-2">
                                        <Label
                                            htmlFor="appSpecificPassword"
                                            className="text-sm font-medium text-black"
                                        >
                                            {t(
                                                'agent.mobilePublish.testflightWizard.appSetup.appSpecificPasswordLabel'
                                            )}{' '}
                                            <span className="text-red-500">
                                                *
                                            </span>
                                        </Label>
                                        {hasStoredAppSpecificPassword ? (
                                            <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                                                <CheckCircle2 className="w-4 h-4 text-green-600" />
                                                <span className="text-sm text-green-800">
                                                    {t(
                                                        'agent.mobilePublish.testflightWizard.appSetup.appSpecificPasswordSaved'
                                                    )}
                                                </span>
                                                <button
                                                    onClick={() => {
                                                        setHasStoredAppSpecificPassword(
                                                            false
                                                        )
                                                        setAppSpecificPassword(
                                                            ''
                                                        )
                                                    }}
                                                    className="ml-auto text-xs text-blue-600 hover:underline"
                                                >
                                                    {t(
                                                        'agent.mobilePublish.testflightWizard.appSetup.change'
                                                    )}
                                                </button>
                                            </div>
                                        ) : (
                                            <>
                                                <Input
                                                    id="appSpecificPassword"
                                                    type="password"
                                                    placeholder={t(
                                                        'agent.mobilePublish.testflightWizard.appSetup.appSpecificPasswordPlaceholder'
                                                    )}
                                                    value={appSpecificPassword}
                                                    onChange={(e) =>
                                                        setAppSpecificPassword(
                                                            e.target.value
                                                        )
                                                    }
                                                    className={
                                                        DIALOG_INPUT_CLASS_NAME
                                                    }
                                                />
                                                <p className="text-xs text-gray-500">
                                                    {t(
                                                        'agent.mobilePublish.testflightWizard.appSetup.appSpecificPasswordHelpPrefix'
                                                    )}{' '}
                                                    <a
                                                        href="https://appleid.apple.com/account/manage"
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-600 hover:underline"
                                                    >
                                                        {t(
                                                            'agent.mobilePublish.testflightWizard.appSetup.appSpecificPasswordHelpLink'
                                                        )}
                                                    </a>{' '}
                                                    {t(
                                                        'agent.mobilePublish.testflightWizard.appSetup.appSpecificPasswordHelpSuffix'
                                                    )}
                                                </p>
                                            </>
                                        )}
                                    </div>
                                    <Button
                                        onClick={handleAppSetup}
                                        disabled={
                                            isLoading ||
                                            (!hasStoredAppSpecificPassword &&
                                                !appSpecificPassword.trim())
                                        }
                                        className="w-full bg-sky-blue text-black"
                                    >
                                        {isLoading ? (
                                            <>
                                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                                {t(
                                                    'agent.mobilePublish.testflightWizard.appSetup.settingUp'
                                                )}
                                            </>
                                        ) : (
                                            t(
                                                'agent.mobilePublish.testflightWizard.appSetup.continueToBuild'
                                            )
                                        )}
                                    </Button>
                                </>
                            )}
                        </div>
                    )}

                    {/* Step 6: Building */}
                    {currentStep === 'building' && (
                        <div className="space-y-4">
                            <div className="flex items-center gap-3 mb-4">
                                {buildStatus === 'running' && (
                                    <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                                )}
                                {buildStatus === 'completed' && (
                                    <CheckCircle2 className="w-6 h-6 text-green-500" />
                                )}
                                {buildStatus === 'failed' && (
                                    <Icon
                                        name="alert-circle"
                                        className="w-6 h-6 text-red-500"
                                    />
                                )}
                                <div>
                                    <h3 className="font-medium text-black">
                                        {buildStatus === 'running' &&
                                            t(
                                                'agent.mobilePublish.testflightWizard.build.statusRunning'
                                            )}
                                        {buildStatus === 'completed' &&
                                            t(
                                                'agent.mobilePublish.testflightWizard.build.statusCompleted'
                                            )}
                                        {buildStatus === 'failed' &&
                                            t(
                                                'agent.mobilePublish.testflightWizard.build.statusFailed'
                                            )}
                                    </h3>
                                    <p className="text-sm text-gray-500">
                                        {buildStatus === 'running' &&
                                            t(
                                                'agent.mobilePublish.testflightWizard.build.detailRunning'
                                            )}
                                        {buildStatus === 'completed' &&
                                            t(
                                                'agent.mobilePublish.testflightWizard.build.detailCompleted'
                                            )}
                                        {buildStatus === 'failed' &&
                                            t(
                                                'agent.mobilePublish.testflightWizard.build.detailFailed'
                                            )}
                                    </p>
                                </div>
                            </div>
                            <div className="bg-gray-900 rounded-xl p-4 max-h-64 overflow-y-auto">
                                <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono break-all">
                                    {buildLogs.length > 0
                                        ? buildLogs.join('\n\n')
                                        : t(
                                              'agent.mobilePublish.testflightWizard.build.waiting'
                                          )}
                                </pre>
                            </div>
                            {buildStatus === 'completed' && (
                                <Button
                                    onClick={() => onOpenChange(false)}
                                    className="w-full bg-green-500 text-white hover:bg-green-600"
                                >
                                    {t(
                                        'agent.mobilePublish.testflightWizard.build.done'
                                    )}
                                </Button>
                            )}
                            {buildStatus === 'failed' && (
                                <Button
                                    onClick={() => setCurrentStep('app_setup')}
                                    variant="outline"
                                    className="w-full text-black"
                                >
                                    {t(
                                        'agent.mobilePublish.testflightWizard.build.tryAgain'
                                    )}
                                </Button>
                            )}
                        </div>
                    )}

                    {/* Error Display */}
                    {error && (
                        <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-xl">
                            <Icon
                                name="alert-circle"
                                className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5"
                            />
                            <div className="text-sm text-red-800">{error}</div>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    )
}
