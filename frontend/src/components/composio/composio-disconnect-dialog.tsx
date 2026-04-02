import { Trans, useTranslation } from 'react-i18next'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type { ComposioProfile } from '@/state/api/composio.api'

interface ComposioDisconnectDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    profile: ComposioProfile
    onConfirm: () => void
}

export function ComposioDisconnectDialog({
    open,
    onOpenChange,
    profile,
    onConfirm
}: ComposioDisconnectDialogProps) {
    const { t } = useTranslation()

    return (
        <AlertDialog open={open} onOpenChange={onOpenChange}>
            <AlertDialogContent className="max-w-md bg-white border-gray-200">
                <AlertDialogHeader>
                    <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
                        <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </div>
                    <AlertDialogTitle className="text-center text-xl font-semibold text-gray-900">
                        {t('composio.disconnectDialog.title', { appName: profile.toolkit_name })}
                    </AlertDialogTitle>
                    <AlertDialogDescription className="text-center text-sm text-gray-600 leading-relaxed pt-2">
                        <Trans
                            i18nKey="composio.disconnectDialog.description"
                            values={{ profileName: profile.profile_name, appName: profile.toolkit_name }}
                            components={{ profileName: <span className="font-medium text-gray-900" /> }}
                        />
                        <br /><br />
                        <span className="text-red-600 font-medium">{t('composio.disconnectDialog.warning')}</span>
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2 sm:gap-3 mt-6">
                    <AlertDialogCancel className="w-full sm:w-auto h-11 border-gray-200 hover:bg-gray-50 font-medium">
                        {t('composio.disconnectDialog.cancel')}
                    </AlertDialogCancel>
                    <AlertDialogAction
                        onClick={onConfirm}
                        className="w-full sm:w-auto h-11 bg-red-600 hover:bg-red-700 text-white font-medium shadow-sm"
                    >
                        {t('composio.disconnectDialog.disconnect')}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    )
}
