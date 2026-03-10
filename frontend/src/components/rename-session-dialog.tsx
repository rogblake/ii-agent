import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle
} from './ui/alert-dialog'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { useAppDispatch } from '@/state'
import { updateSession } from '@/state/slice/sessions'
import { fetchPins } from '@/state/slice/pins'
import { ISession } from '@/typings/agent'

type RenameSessionDialogProps = {
    session: ISession
    open: boolean
    onOpenChange: (open: boolean) => void
}

const RenameSessionDialog = ({
    session,
    open,
    onOpenChange
}: RenameSessionDialogProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const [newName, setNewName] = useState(session.name || '')

    const renameTitle =
        session.agent_type === 'chat'
            ? t('sessions.renameChat')
            : t('sessions.renameProject')
    const renameDescription =
        session.agent_type === 'chat'
            ? t('sessions.renameDescriptionChat')
            : t('sessions.renameDescriptionProject')
    const inputId = `session-name-${session.id}`

    useEffect(() => {
        if (open) {
            setNewName(session.name || '')
        }
    }, [open, session.name])

    const handleOpenChange = (nextOpen: boolean) => {
        if (!nextOpen) {
            setNewName(session.name || '')
        }
        onOpenChange(nextOpen)
    }

    const confirmRename = async () => {
        const trimmedName = newName.trim()
        if (!trimmedName || trimmedName === session.name) {
            handleOpenChange(false)
            return
        }

        try {
            await dispatch(
                updateSession({
                    sessionId: session.id,
                    name: trimmedName
                })
            ).unwrap()
            // Refresh pinned sessions so sidebar stubs reflect the new name
            dispatch(fetchPins())
            handleOpenChange(false)
        } catch (error) {
            console.error('Failed to rename session:', error)
        }
    }

    const cancelRename = () => {
        handleOpenChange(false)
    }

    return (
        <AlertDialog open={open} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{renameTitle}</AlertDialogTitle>
                    <AlertDialogDescription>
                        {renameDescription}
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <div className="py-4">
                    <Label htmlFor={inputId} className="text-sm text-black">
                        {t('sessions.nameLabel')}
                    </Label>
                    <Input
                        id={inputId}
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                confirmRename()
                            }
                        }}
                        placeholder={t('sessions.namePlaceholder')}
                        className="mt-2 text-black dark:text-black dark:bg-grey-3 dark:border-grey"
                        autoFocus
                    />
                </div>
                <AlertDialogFooter>
                    <AlertDialogCancel onClick={cancelRename}>
                        {t('common.cancel')}
                    </AlertDialogCancel>
                    <AlertDialogAction
                        className="bg-firefly dark:bg-sky-blue text-sky-blue dark:text-black"
                        onClick={confirmRename}
                    >
                        {t('common.rename')}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    )
}

export default RenameSessionDialog
