import { useState, useCallback } from 'react'
import isEmpty from 'lodash/isEmpty'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import SessionItem from './session-item'
import { Skeleton } from './ui/skeleton'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from './ui/collapsible'
import {
    selectChats,
    selectActiveSessionId,
    useAppSelector,
    useAppDispatch,
    bulkDeleteSessions
} from '@/state'
import { clearSessionState } from '@/state/slice/session-state'
import { Icon } from './ui/icon'
import { Button } from './ui/button'
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
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger
} from '@/components/ui/tooltip'

interface ChatListProps {
    workspaceInfo?: string
    isLoading: boolean
    loadingMore: boolean
    handleResetState: () => void
}

const ChatList = ({
    workspaceInfo,
    isLoading,
    loadingMore,
    handleResetState
}: ChatListProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const chats = useAppSelector(selectChats)
    const activeSessionId = useAppSelector(selectActiveSessionId)

    const [isCollapsibleOpen, setIsCollapsibleOpen] = useState(true)
    const [selectionMode, setSelectionMode] = useState(false)
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
    const [isDeleting, setIsDeleting] = useState(false)

    const filteredChats = chats?.filter((session) => session.name) ?? []

    const toggleSelectionMode = () => {
        if (selectionMode) {
            // Exiting selection mode - clear selections
            setSelectedIds(new Set())
        }
        setSelectionMode(!selectionMode)
    }

    const handleSelectionChange = useCallback(
        (sessionId: string, selected: boolean) => {
            setSelectedIds((prev) => {
                const next = new Set(prev)
                if (selected) {
                    next.add(sessionId)
                } else {
                    next.delete(sessionId)
                }
                return next
            })
        },
        []
    )

    const handleSelectAll = () => {
        if (selectedIds.size === filteredChats.length) {
            setSelectedIds(new Set())
        } else {
            setSelectedIds(new Set(filteredChats.map((s) => s.id)))
        }
    }

    const handleBulkDelete = () => {
        if (selectedIds.size === 0) return
        setIsDeleteDialogOpen(true)
    }

    const confirmBulkDelete = async () => {
        setIsDeleting(true)
        try {
            const ids = Array.from(selectedIds)
            const result = await dispatch(bulkDeleteSessions(ids)).unwrap()

            // Clear cached session state for deleted sessions
            for (const id of result.deleted_ids) {
                dispatch(clearSessionState(id))
            }

            if (result.deleted_ids.length > 0) {
                toast.success(
                    t('sidebar.bulkDeleteSuccess', {
                        count: result.deleted_ids.length
                    })
                )
            }
            if (result.failed_ids.length > 0) {
                toast.error(
                    t('sidebar.bulkDeletePartialFailure', {
                        count: result.failed_ids.length
                    })
                )
            }

            setSelectedIds(new Set())
            setSelectionMode(false)
        } catch (error) {
            console.error('Failed to bulk delete sessions:', error)
            toast.error(t('sidebar.bulkDeleteError'))
        } finally {
            setIsDeleting(false)
            setIsDeleteDialogOpen(false)
        }
    }

    return (
        <Collapsible
            open={isCollapsibleOpen}
            onOpenChange={setIsCollapsibleOpen}
            className="group-data-[collapsible=icon]:hidden"
        >
            <div className="flex items-center justify-between">
                <CollapsibleTrigger className="flex-1">
                    <div className="w-full justify-start !text-[14px] rounded-xl cursor-pointer flex items-center gap-x-[6px]">
                        <span className="text-black/[0.56] dark:text-white/[0.56]">
                            {t('sidebar.chats')}
                        </span>
                        <Icon
                            name="arrow-down"
                            className={`size-[18px] fill-black/[0.56] dark:fill-white/[0.56] transition-transform duration-200 ${
                                isCollapsibleOpen ? 'rotate-180' : ''
                            }`}
                        />
                    </div>
                </CollapsibleTrigger>
                {isCollapsibleOpen && filteredChats.length > 0 && (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="!p-0 !h-auto z-10"
                                onClick={toggleSelectionMode}
                                aria-label={
                                    selectionMode
                                        ? t('common.cancel')
                                        : t('sidebar.selectChats')
                                }
                            >
                                <Icon
                                    name={
                                        selectionMode
                                            ? 'close'
                                            : 'document-check'
                                    }
                                    className={`size-[18px] ${
                                        selectionMode
                                            ? 'fill-black dark:fill-white'
                                            : 'fill-black/[0.56] dark:fill-white/[0.56]'
                                    }`}
                                />
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                            {selectionMode
                                ? t('common.cancel')
                                : t('sidebar.selectChats')}
                        </TooltipContent>
                    </Tooltip>
                )}
            </div>
            <CollapsibleContent className="mt-3">
                {selectionMode && (
                    <div className="flex items-center gap-x-2 mb-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="!px-0 !h-auto text-xs font-normal"
                            onClick={handleSelectAll}
                        >
                            {selectedIds.size === filteredChats.length
                                ? t('sidebar.deselectAll')
                                : t('sidebar.selectAll')}
                        </Button>
                        {selectedIds.size > 0 && (
                            <Button
                                variant="ghost"
                                size="sm"
                                className="!px-0 !h-auto text-xs font-normal text-red-2"
                                onClick={handleBulkDelete}
                            >
                                <Icon
                                    name="trash"
                                    className="size-3.5 fill-red-2"
                                />
                                {t('sidebar.deleteSelected', {
                                    count: selectedIds.size
                                })}
                            </Button>
                        )}
                    </div>
                )}
                <div className="space-y-[6px] text-[14px]">
                    {isLoading && isEmpty(chats) && (
                        <div className="px-2 space-y-4">
                            <Skeleton className="h-4 w-full !bg-black/10 dark:!bg-white/10" />
                            <Skeleton className="h-4 w-full !bg-black/10 dark:!bg-white/10" />
                            <Skeleton className="h-4 w-full !bg-black/10 dark:!bg-white/10" />
                        </div>
                    )}
                    {filteredChats.map((session) => (
                        <SessionItem
                            key={session.id}
                            session={session}
                            isActive={
                                activeSessionId === session.id ||
                                (workspaceInfo?.includes(session.id) ?? false)
                            }
                            onClick={handleResetState}
                            selectionMode={selectionMode}
                            isSelected={selectedIds.has(session.id)}
                            onSelectionChange={handleSelectionChange}
                        />
                    ))}
                    {loadingMore && (
                        <div className="text-center py-2 text-gray-500">
                            {t('common.loadingMore')}
                        </div>
                    )}
                </div>
            </CollapsibleContent>
            <AlertDialog
                open={isDeleteDialogOpen}
                onOpenChange={setIsDeleteDialogOpen}
            >
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            {t('sidebar.bulkDeleteChatsTitle')}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('sidebar.bulkDeleteChatsConfirmation', {
                                count: selectedIds.size
                            })}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={isDeleting}>
                            {t('common.cancel')}
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmBulkDelete}
                            className="bg-red-2 hover:bg-red-2 text-white"
                            disabled={isDeleting}
                        >
                            {isDeleting
                                ? t('common.loading')
                                : t('common.delete')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </Collapsible>
    )
}

export default ChatList
