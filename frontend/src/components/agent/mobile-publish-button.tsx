'use client'

import { useState } from 'react'
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
import { Icon } from '@/components/ui/icon'
import { TestflightWizardDialog } from '@/components/agent/testflight-wizard-dialog'

interface MobilePublishButtonProps {
    variant?: 'default' | 'outline' | 'ghost'
    size?: 'default' | 'sm' | 'lg' | 'icon'
    className?: string
}

type StoreOption = 'app_store' | 'google_play' | null

export const MobilePublishButton = ({
    variant = 'default',
    size = 'sm',
    className = ''
}: MobilePublishButtonProps) => {
    const { t } = useTranslation()

    const [isStoreDialogOpen, setStoreDialogOpen] = useState(false)
    const [isTestflightWizardOpen, setTestflightWizardOpen] = useState(false)

    const handlePublishClick = () => {
        setStoreDialogOpen(true)
    }

    const handleStoreSelect = (store: StoreOption) => {
        if (store === 'google_play') {
            window.open(
                'https://docs.expo.dev/deploy/submit-to-app-stores/',
                '_blank',
                'noopener'
            )
            setStoreDialogOpen(false)
        } else if (store === 'app_store') {
            setStoreDialogOpen(false)
            setTestflightWizardOpen(true)
        }
    }

    return (
        <>
            <Button
                size={size}
                variant={variant}
                className={className}
                onClick={handlePublishClick}
            >
                {t('agent.publish.publish')}
            </Button>

            {/* Store Selection Dialog */}
            <Dialog open={isStoreDialogOpen} onOpenChange={setStoreDialogOpen}>
                <DialogContent className="!bg-white text-black rounded-2xl border border-grey/70 dark:border-sky-blue-2/30 shadow-btn backdrop-blur-xl p-6 md:p-8 max-w-md">
                    <DialogHeader className="gap-1">
                        <DialogTitle className="text-2xl font-semibold text-black">
                            {t('agent.mobilePublish.storeDialog.title')}
                        </DialogTitle>
                        <DialogDescription className="text-sm text-black">
                            {t('agent.mobilePublish.storeDialog.description')}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="flex flex-col gap-3 mt-4">
                        <button
                            onClick={() => handleStoreSelect('app_store')}
                            className="flex items-center gap-4 p-4 rounded-xl border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-all cursor-pointer"
                        >
                            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-black">
                                <Icon
                                    name="apple"
                                    className="w-7 h-7 fill-white"
                                />
                            </div>
                            <div className="flex flex-col items-start">
                                <span className="font-semibold text-black">
                                    {t('agent.mobilePublish.storeDialog.appStore')}
                                </span>
                                <span className="text-sm text-gray-500">
                                    {t('agent.mobilePublish.storeDialog.appStoreDescription')}
                                </span>
                            </div>
                        </button>
                        <button
                            onClick={() => handleStoreSelect('google_play')}
                            className="flex items-center gap-4 p-4 rounded-xl border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-all cursor-pointer"
                        >
                            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-green-400 via-blue-500 to-purple-500">
                                <Icon
                                    name="google-play"
                                    className="w-6 h-6 fill-white"
                                />
                            </div>
                            <div className="flex flex-col items-start">
                                <span className="font-semibold text-black">
                                    {t('agent.mobilePublish.storeDialog.googlePlay')}
                                </span>
                                <span className="text-sm text-gray-500">
                                    {t('agent.mobilePublish.storeDialog.googlePlayDescription')}
                                </span>
                            </div>
                        </button>
                    </div>
                    <DialogFooter className="sm:justify-end mt-4">
                        <Button
                            variant="outline"
                            onClick={() => setStoreDialogOpen(false)}
                            className="text-black"
                        >
                            {t('common.cancel')}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* TestFlight Wizard Dialog (New Replit-like flow) */}
            <TestflightWizardDialog
                open={isTestflightWizardOpen}
                onOpenChange={setTestflightWizardOpen}
            />
        </>
    )
}
