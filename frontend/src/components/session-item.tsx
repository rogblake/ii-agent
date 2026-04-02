'use client'

import { useState } from 'react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import { Icon } from './ui/icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from './ui/dropdown-menu'
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
import RenameSessionDialog from './rename-session-dialog'
import ShareConversation from './agent/share-conversation'
import { useAppDispatch } from '@/state'
import { deleteSession } from '@/state/slice/sessions'
import { clearSessionState } from '@/state/slice/session-state'
import { Tooltip, TooltipContent } from './ui/tooltip'
import { TooltipTrigger } from '@radix-ui/react-tooltip'
import { ISession } from '@/typings/agent'
import { FEATURES } from '@/constants/tool'
import { useTranslation } from 'react-i18next'
import { Checkbox } from './ui/checkbox'

interface SessionItemProps {
    session: ISession
    isActive: boolean
    onClick: () => void
    selectionMode?: boolean
    isSelected?: boolean
    onSelectionChange?: (sessionId: string, selected: boolean) => void
}

const SessionItem = ({
    session,
    isActive,
    onClick,
    selectionMode = false,
    isSelected = false,
    onSelectionChange
}: SessionItemProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const [isDropdownOpen, setIsDropdownOpen] = useState(false)
    const [isHovered, setIsHovered] = useState(false)
    const [isShareOpen, setIsShareOpen] = useState(false)
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
    const [isRenameDialogOpen, setIsRenameDialogOpen] = useState(false)

    const handlePointerEnter = (event: React.PointerEvent<HTMLDivElement>) => {
        if (event.pointerType === 'mouse' || event.pointerType === 'pen') {
            setIsHovered(true)
        }
    }

    const handlePointerLeave = (event: React.PointerEvent<HTMLDivElement>) => {
        if (event.pointerType === 'mouse' || event.pointerType === 'pen') {
            setIsHovered(false)
        }
    }

    const handleShare = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setIsShareOpen(true)
    }

    const handleRename = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setIsRenameDialogOpen(true)
        setIsDropdownOpen(false)
    }

    const handleDelete = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setIsDeleteDialogOpen(true)
    }

    const confirmDelete = async () => {
        try {
            await dispatch(deleteSession(session.id)).unwrap()
            // Clear cached session state to free up localStorage
            dispatch(clearSessionState(session.id))
            setIsDeleteDialogOpen(false)
        } catch (error) {
            console.error('Failed to delete session:', error)
            // You might want to show a toast notification here
        }
    }

    const cancelDelete = () => {
        setIsDeleteDialogOpen(false)
    }

    const handleCheckboxClick = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        onSelectionChange?.(session.id, !isSelected)
    }

    const handleRowClickInSelectionMode = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        onSelectionChange?.(session.id, !isSelected)
    }

    return (
        <div
            className={cn(
                'relative flex items-center gap-x-2 rounded-lg py-1 before:hidden hover:before:block before:absolute before:-left-10 before:top-0 before:-bottom-0 before:w-200 md:before:w-100 before:bg-firefly/10 dark:before:bg-sky-blue-2/10',
                {
                    'before:block':
                        isActive || isHovered || isDropdownOpen || isSelected
                }
            )}
            onPointerEnter={handlePointerEnter}
            onPointerLeave={handlePointerLeave}
        >
            {selectionMode && (
                <div
                    className="z-10 flex items-center cursor-pointer"
                    onClick={handleCheckboxClick}
                >
                    <Checkbox
                        checked={isSelected}
                        className="size-4"
                        tabIndex={-1}
                    />
                </div>
            )}
            <Tooltip>
                <TooltipTrigger asChild>
                    {selectionMode ? (
                        <div
                            onClick={handleRowClickInSelectionMode}
                            className={cn(
                                'flex-1 line-clamp-1 z-10 flex items-center gap-x-[6px] cursor-pointer'
                            )}
                        >
                            {session.agent_type !== 'chat' && (
                                <Icon
                                    name={
                                        FEATURES.find(
                                            (feature) =>
                                                feature.type ===
                                                session.agent_type
                                        )?.icon || 'global'
                                    }
                                    className="fill-black dark:fill-white size-5"
                                />
                            )}
                            <span className="flex-1 line-clamp-1">
                                {session.name}
                            </span>
                        </div>
                    ) : (
                        <Link
                            to={
                                session.agent_type === 'chat'
                                    ? `/chat?id=${session.id}`
                                    : `/${session.id}`
                            }
                            onClick={onClick}
                            className={cn(
                                'flex-1 line-clamp-1 z-10 flex items-center gap-x-[6px]'
                            )}
                        >
                            {session.agent_type !== 'chat' && (
                                <Icon
                                    name={
                                        FEATURES.find(
                                            (feature) =>
                                                feature.type ===
                                                session.agent_type
                                        )?.icon || 'global'
                                    }
                                    className="fill-black dark:fill-white size-5"
                                />
                            )}
                            <span className="flex-1 line-clamp-1">
                                {session.name}
                            </span>
                        </Link>
                    )}
                </TooltipTrigger>
                <TooltipContent
                    align="center"
                    side="right"
                    className="max-w-[200px]"
                >
                    {session.name}
                </TooltipContent>
            </Tooltip>
            {!selectionMode && (
                <DropdownMenu
                    open={isDropdownOpen}
                    onOpenChange={setIsDropdownOpen}
                >
                    <DropdownMenuTrigger
                        onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                        }}
                        className={cn(
                            'transition-opacity z-10 cursor-pointer',
                            isHovered || isDropdownOpen
                                ? 'opacity-100'
                                : 'opacity-0'
                        )}
                    >
                        <Icon
                            name="more-2"
                            className="size-4 stroke-black dark:stroke-white"
                        />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                        align="end"
                        className="w-[185px] px-4 py-2"
                    >
                        <DropdownMenuItem
                            className="py-2"
                            onClick={handleShare}
                        >
                            <Icon
                                name="share"
                                className="size-5 stroke-black"
                            />
                            {t('common.share')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            className="py-2"
                            onClick={handleRename}
                        >
                            <Icon
                                name="edit"
                                className="size-[18px] fill-black"
                            />
                            {t('common.rename')}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator className="my-1" />
                        <DropdownMenuItem
                            onClick={handleDelete}
                            variant="destructive"
                            className="text-red-2 py-2"
                        >
                            <Icon name="trash" className="size-5" />
                            {t('common.delete')}
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            )}
            <ShareConversation
                open={isShareOpen}
                onOpenChange={setIsShareOpen}
                sessionId={session.id}
            />
            <AlertDialog
                open={isDeleteDialogOpen}
                onOpenChange={setIsDeleteDialogOpen}
            >
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            {t('dashboard.deleteSession')}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('dashboard.deleteConfirmationNamed', {
                                sessionName: session.name
                            })}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={cancelDelete}>
                            {t('common.cancel')}
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmDelete}
                            className="bg-red-2 hover:bg-red-2 text-white"
                        >
                            {t('common.delete')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
            <RenameSessionDialog
                session={session}
                open={isRenameDialogOpen}
                onOpenChange={setIsRenameDialogOpen}
            />
        </div>
    )
}

export default SessionItem
