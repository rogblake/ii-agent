'use client'

import { useState } from 'react'
import {
    Eye,
    EyeOff,
    Lock,
    Key,
    Loader2,
    X,
    Check,
    AlertTriangle
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { useTranslation } from 'react-i18next'
import { selectProjectId, useAppSelector } from '@/state'
import { projectService } from '@/services/project.service'

export interface Secret {
    key: string
    value: string
    description?: string
}

interface SecretsInputProps {
    secrets: Secret[]
    message?: string
    /**
     * When true, displays secrets in read-only mode without input fields or action buttons.
     * Useful for showing previously saved secrets or displaying secrets after submission.
     */
    readOnly?: boolean
    /**
     * Session ID for saving secrets via projectService.
     * Required for interactive mode.
     */
    sessionId?: string
    /**
     * Callback when user confirms (after saving secrets or for "continue anyway").
     * Required for interactive mode.
     */
    onConfirm?: (confirmed: boolean) => void
    /**
     * Callback when user cancels.
     */
    onCancel?: () => void
}

export const SecretsInput = ({
    secrets,
    message,
    readOnly = false,
    sessionId,
    onConfirm,
    onCancel
}: SecretsInputProps) => {
    const { t } = useTranslation()
    const projectId = useAppSelector(selectProjectId)

    const [isSubmitting, setIsSubmitting] = useState(false)
    const [secretValues, setSecretValues] = useState<Record<string, string>>(
        () => {
            const initial: Record<string, string> = {}
            secrets.forEach((secret) => {
                initial[secret.key] = secret.value || ''
            })
            return initial
        }
    )
    const [showValues, setShowValues] = useState(false)

    const handleValueChange = (key: string, value: string) => {
        setSecretValues((prev) => ({
            ...prev,
            [key]: value
        }))
    }

    const handleSecretsSubmit = async () => {
        if (!sessionId || !onConfirm) return

        const secretsObject: Record<string, string> = {}
        secrets.forEach((secret) => {
            const value = secretValues[secret.key]
            if (secret.key && value) {
                secretsObject[secret.key] = value
            }
        })

        if (Object.keys(secretsObject).length === 0) {
            toast.error(t('agent.secrets.errors.atLeastOneValue'))
            return
        }

        setIsSubmitting(true)
        try {
            // Save secrets using project service
            await projectService.updateProjectSecrets(sessionId, secretsObject)

            toast.success(t('agent.secrets.toasts.saved'))

            // Continue the run after saving secrets
            onConfirm(true)
        } catch (error) {
            console.error('Failed to save secrets:', error)
            toast.error(t('agent.secrets.errors.saveFailed'))
            setIsSubmitting(false)
        }
    }

    // Determine if we're in interactive mode
    const isInteractive = !readOnly && sessionId && onConfirm

    // Show project not initialized warning for interactive mode
    if (isInteractive && !projectId) {
        return (
            <div className="mt-3 border border-grey rounded-xl p-4 bg-firefly/[0.18] dark:bg-sky-blue/[0.18]">
                <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="size-4 text-firefly dark:text-sky-blue" />
                    <span className="text-sm font-medium text-firefly dark:text-sky-blue">
                        {t('agent.secrets.projectNotInited')}
                    </span>
                </div>
                <Button
                    onClick={() => onConfirm(true)}
                    className="w-full bg-firefly text-sky-blue dark:bg-sky-blue dark:text-black font-medium py-2 px-4 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2 hover:opacity-90"
                >
                    <Check className="size-4" />
                    {t('agent.secrets.continueAnyway')}
                </Button>
            </div>
        )
    }

    return (
        <div className="mt-3 space-y-3 bg-firefly/[0.18] dark:bg-sky-blue/[0.18] border border-grey rounded-xl p-4">
            <div className="flex items-center gap-2">
                <Lock className="size-4" />
                <span className="text-sm font-medium">
                    {t('agent.secrets.environmentVariables')}
                </span>
            </div>

            {message && <p className="text-xs text-gray-400">{message}</p>}

            <div className="space-y-3">
                {secrets.map((secret) => (
                    <div key={secret.key} className="space-y-1.5">
                        <div className="flex items-center gap-2">
                            <Key className="size-3 text-gray-400" />
                            <span className="text-sm font-medium">
                                {secret.key}
                            </span>
                        </div>
                        {secret.description && (
                            <p className="text-xs text-gray-400 pl-5">
                                {secret.description}
                            </p>
                        )}
                        {readOnly ? (
                            <div className="flex items-center gap-2 pl-5">
                                <span className="text-xs text-gray-500">
                                    {showValues
                                        ? secret.value || '(empty)'
                                        : secret.value
                                          ? '••••••••'
                                          : '(empty)'}
                                </span>
                                {secret.value && (
                                    <button
                                        onClick={() =>
                                            setShowValues(!showValues)
                                        }
                                        className="cursor-pointer p-0.5 hover:bg-white/10 rounded transition-colors"
                                    >
                                        {showValues ? (
                                            <EyeOff className="size-3 text-gray-400" />
                                        ) : (
                                            <Eye className="size-3 text-gray-400" />
                                        )}
                                    </button>
                                )}
                            </div>
                        ) : (
                            <div className="relative">
                                <Input
                                    type={showValues ? 'text' : 'password'}
                                    value={secretValues[secret.key] || ''}
                                    onChange={(e) =>
                                        handleValueChange(
                                            secret.key,
                                            e.target.value
                                        )
                                    }
                                    className="h-9 text-sm bg-white dark:bg-[#A6FFFF1A] border-grey rounded-lg pr-10"
                                    placeholder={t('agent.secrets.placeholder', {
                                        key: secret.key
                                    })}
                                    disabled={isSubmitting}
                                />
                                <button
                                    onClick={() => setShowValues(!showValues)}
                                    className="cursor-pointer absolute top-[10px] right-2 p-0.5 hover:bg-white/10 rounded transition-colors"
                                    disabled={isSubmitting}
                                >
                                    {showValues ? (
                                        <EyeOff className="size-3" />
                                    ) : (
                                        <Eye className="size-3" />
                                    )}
                                </button>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {isInteractive && (
                <div className="flex gap-2 pt-1">
                    <Button
                        onClick={handleSecretsSubmit}
                        disabled={isSubmitting}
                        className="text-xs font-semibold bg-firefly text-sky-blue dark:bg-sky-blue dark:text-black hover:opacity-90"
                    >
                        {isSubmitting ? (
                            <>
                                <Loader2 className="size-3 mr-1 animate-spin" />
                                {t('common.saving')}
                            </>
                        ) : (
                            t('common.continue')
                        )}
                    </Button>
                    {onCancel && (
                        <Button
                            onClick={onCancel}
                            disabled={isSubmitting}
                            variant="outline"
                            className="text-xs font-semibold border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                            <X className="size-3 mr-1" />
                            {t('common.cancel')}
                        </Button>
                    )}
                </div>
            )}
        </div>
    )
}
