'use client'

import { useState } from 'react'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Icon } from '@/components/ui/icon'
import { mobileAppService } from '@/services/mobile-app.service'
import type { ChatMessagePayload } from '@/typings/agent'

interface TestflightDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    sendMessage: (payload: ChatMessagePayload) => boolean
}

export const TestflightDialog = ({
    open,
    onOpenChange,
    sendMessage
}: TestflightDialogProps) => {
    const { t } = useTranslation()
    const { sessionId } = useParams<{ sessionId: string }>()
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [formData, setFormData] = useState({
        expoToken: '',
        appleId: '',
        appSpecificPassword: '',
        teamId: ''
    })

    const handleInputChange = (field: string, value: string) => {
        setFormData((prev) => ({ ...prev, [field]: value }))
    }

    const handleSubmit = async () => {
        if (!formData.expoToken.trim()) {
            toast.error(t('agent.mobilePublish.errors.expoTokenRequired'))
            return
        }

        if (!formData.appleId.trim()) {
            toast.error(t('agent.mobilePublish.errors.appleIdRequired'))
            return
        }

        if (!formData.appSpecificPassword.trim()) {
            toast.error(
                t('agent.mobilePublish.errors.appSpecificPasswordRequired')
            )
            return
        }

        setIsSubmitting(true)

        try {
            await mobileAppService.submitToTestflight({
                expoToken: formData.expoToken.trim(),
                appleId: formData.appleId.trim(),
                appSpecificPassword: formData.appSpecificPassword.trim(),
                teamId: formData.teamId.trim() || undefined,
                sessionId: sessionId || '',
                sendMessage
            })

            toast.success(t('agent.mobilePublish.toasts.submissionStarted'))
            onOpenChange(false)
        } catch (error) {
            toast.error(
                error instanceof Error
                    ? error.message
                    : t('agent.mobilePublish.errors.submissionFailed')
            )
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleOpenDocs = () => {
        window.open('https://docs.expo.dev/submit/ios/', '_blank', 'noopener')
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="!bg-white text-black rounded-2xl border border-grey/70 dark:border-sky-blue-2/30 shadow-btn backdrop-blur-xl p-6 md:p-8 max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader className="gap-1">
                    <DialogTitle className="text-2xl font-semibold text-black">
                        {t('agent.mobilePublish.testflightDialog.title')}
                    </DialogTitle>
                    <DialogDescription className="text-sm text-black">
                        {t('agent.mobilePublish.testflightDialog.description')}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-5 mt-4">
                    {/* Expo Token */}
                    <div className="space-y-2">
                        <Label
                            htmlFor="expoToken"
                            className="text-sm font-medium text-black"
                        >
                            {t(
                                'agent.mobilePublish.testflightDialog.expoTokenLabel'
                            )}{' '}
                            <span className="text-red-500">*</span>
                        </Label>
                        <Input
                            id="expoToken"
                            type="password"
                            placeholder={t(
                                'agent.mobilePublish.testflightDialog.expoTokenPlaceholder'
                            )}
                            value={formData.expoToken}
                            onChange={(e) =>
                                handleInputChange('expoToken', e.target.value)
                            }
                            className="!text-black placeholder:text-black/50 !bg-black/10"
                        />
                        <p className="text-xs text-gray-500">
                            <a
                                href="https://expo.dev/settings/access-tokens"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:underline"
                            >
                                {t(
                                    'agent.mobilePublish.testflightDialog.getFromExpo'
                                )}
                            </a>
                        </p>
                    </div>

                    {/* Apple ID */}
                    <div className="space-y-2">
                        <Label
                            htmlFor="appleId"
                            className="text-sm font-medium text-black"
                        >
                            {t(
                                'agent.mobilePublish.testflightDialog.appleIdLabel'
                            )}{' '}
                            <span className="text-red-500">*</span>
                        </Label>
                        <Input
                            id="appleId"
                            type="email"
                            placeholder={t(
                                'agent.mobilePublish.testflightDialog.appleIdPlaceholder'
                            )}
                            value={formData.appleId}
                            onChange={(e) =>
                                handleInputChange('appleId', e.target.value)
                            }
                            className="!text-black placeholder:text-black/50 !bg-black/10"
                        />
                        <p className="text-xs text-gray-500">
                            {t(
                                'agent.mobilePublish.testflightDialog.appleIdDescription'
                            )}
                        </p>
                    </div>

                    {/* App-Specific Password */}
                    <div className="space-y-2">
                        <Label
                            htmlFor="appSpecificPassword"
                            className="text-sm font-medium text-black"
                        >
                            {t(
                                'agent.mobilePublish.testflightDialog.appSpecificPasswordLabel'
                            )}{' '}
                            <span className="text-red-500">*</span>
                        </Label>
                        <Input
                            id="appSpecificPassword"
                            type="password"
                            placeholder={t(
                                'agent.mobilePublish.testflightDialog.appSpecificPasswordPlaceholder'
                            )}
                            value={formData.appSpecificPassword}
                            onChange={(e) =>
                                handleInputChange(
                                    'appSpecificPassword',
                                    e.target.value
                                )
                            }
                            className="!text-black placeholder:text-black/50 !bg-black/10"
                        />
                        <p className="text-xs text-gray-500">
                            <a
                                href="https://support.apple.com/en-us/102654"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:underline"
                            >
                                {t(
                                    'agent.mobilePublish.testflightDialog.generateAtApple'
                                )}
                            </a>
                        </p>
                    </div>

                    {/* Team ID (Optional) */}
                    <div className="space-y-2">
                        <Label
                            htmlFor="teamId"
                            className="text-sm font-medium text-black"
                        >
                            {t(
                                'agent.mobilePublish.testflightDialog.teamIdLabel'
                            )}{' '}
                            <span className="text-gray-400">
                                ({t('common.optional')})
                            </span>
                        </Label>
                        <Input
                            id="teamId"
                            type="text"
                            placeholder={t(
                                'agent.mobilePublish.testflightDialog.teamIdPlaceholder'
                            )}
                            value={formData.teamId}
                            onChange={(e) =>
                                handleInputChange('teamId', e.target.value)
                            }
                            className="!text-black placeholder:text-black/50 !bg-black/10"
                        />
                        <p className="text-xs text-gray-500">
                            {t(
                                'agent.mobilePublish.testflightDialog.teamIdDescription'
                            )}
                        </p>
                    </div>

                    {/* Info box */}
                    <div className="flex items-start gap-3 p-4 bg-blue-50 border border-blue-200 rounded-xl">
                        <Icon
                            name="info-circle"
                            className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
                        />
                        <div className="text-sm text-blue-800">
                            <p className="font-medium mb-1">
                                {t(
                                    'agent.mobilePublish.testflightDialog.infoTitle'
                                )}
                            </p>
                            <p className="text-blue-700">
                                {t(
                                    'agent.mobilePublish.testflightDialog.infoDescription'
                                )}
                            </p>
                        </div>
                    </div>
                </div>

                <DialogFooter className="sm:justify-end gap-3 mt-6">
                    <Button
                        variant="outline"
                        onClick={handleOpenDocs}
                        className="text-black"
                    >
                        {t('agent.mobilePublish.testflightDialog.viewDocs')}
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={isSubmitting}
                        className="bg-sky-blue text-black"
                    >
                        {isSubmitting ? (
                            <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                {t(
                                    'agent.mobilePublish.testflightDialog.submitting'
                                )}
                            </>
                        ) : (
                            t('agent.mobilePublish.testflightDialog.submit')
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
