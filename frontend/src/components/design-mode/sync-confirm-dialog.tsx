import type { ReactNode } from 'react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogTitle
} from '@/components/ui/alert-dialog'
import { Icon } from '@/components/ui/icon'
import { cn } from '@/lib/utils'

interface SyncConfirmDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    pendingChangesCount: number
    onConfirm: () => void
    title?: ReactNode
    description?: ReactNode
    confirmLabel?: ReactNode
}

export function SyncConfirmDialog({
    open,
    onOpenChange,
    pendingChangesCount,
    onConfirm,
    title,
    description: descriptionProp,
    confirmLabel
}: SyncConfirmDialogProps) {
    const { t } = useTranslation()

    const description = useMemo(() => {
        if (descriptionProp !== undefined) return descriptionProp
        if (pendingChangesCount <= 0) {
            return t('designMode.syncDialog.descriptionEmpty')
        }
        return t('designMode.syncDialog.description', {
            count: pendingChangesCount
        })
    }, [descriptionProp, pendingChangesCount, t])

    return (
        <AlertDialog open={open} onOpenChange={onOpenChange}>
            <AlertDialogContent
                data-design-mode-preserve-selection
                className="w-[640px] h-[232px] max-w-[calc(100%-2rem)] rounded-[12px] p-0 border-0 bg-white shadow-[0px_4px_24px_rgba(255,255,255,0.16)]"
            >
                <div className="relative flex h-full flex-col px-6 py-6">
                    <button
                        type="button"
                        onClick={() => onOpenChange(false)}
                        className={cn(
                            'absolute right-6 top-6 flex h-6 w-6 items-center justify-center transition',
                            'text-black hover:opacity-70 active:scale-95'
                        )}
                        aria-label={t('common.close')}
                    >
                        <Icon name="close-2" className="size-6" />
                    </button>

                    <AlertDialogTitle className="pr-10 text-[18px] leading-6 font-bold text-[#1B1B1B]">
                        {title ?? t('designMode.syncDialog.title')}
                    </AlertDialogTitle>

                    <div className="mt-6 flex h-[70px] items-start gap-3 rounded-[12px] border-2 border-sky-blue bg-[#FFDE8A]/30 px-4 py-4">
                        <Icon
                            name="danger"
                            className="mt-0.5 size-6 text-[#292D32]"
                        />
                        <AlertDialogDescription className="text-sm leading-[19px] text-black">
                            {description}
                        </AlertDialogDescription>
                    </div>

                    <div className="mt-auto flex items-center gap-2">
                        <AlertDialogAction
                            disabled={pendingChangesCount <= 0}
                            className={cn(
                                'h-[42px] w-[86px] rounded-lg bg-[#BEE6F0] text-[#181E1C] font-bold',
                                'transition hover:brightness-95 disabled:opacity-40'
                            )}
                            onClick={() => {
                                onOpenChange(false)
                                onConfirm()
                            }}
                        >
                            {confirmLabel ?? t('designMode.syncDialog.confirm')}
                        </AlertDialogAction>
                        <AlertDialogCancel
                            className={cn(
                                'h-[42px] w-[114px] rounded-lg border-transparent bg-transparent px-0 text-[#181E1C] font-bold',
                                'transition hover:bg-black/5 hover:text-[#181E1C]'
                            )}
                        >
                            {t('common.keepEditing')}
                        </AlertDialogCancel>
                    </div>
                </div>
            </AlertDialogContent>
        </AlertDialog>
    )
}
