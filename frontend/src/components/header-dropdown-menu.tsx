import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Icon } from '@/components/ui/icon'
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger
} from '@/components/ui/tooltip'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import RenameSessionDialog from '@/components/rename-session-dialog'
import { ISession } from '@/typings/agent'
import clsx from 'clsx'

type HeaderDropdownMenuProps = {
    isFavorite: boolean
    onShare: () => void
    onToggleFavorite: () => void
    onDelete: () => void
    triggerClassName?: string
    session?: ISession
}

const HeaderDropdownMenu = ({
    isFavorite,
    onShare,
    onToggleFavorite,
    onDelete,
    triggerClassName,
    session
}: HeaderDropdownMenuProps) => {
    const { t } = useTranslation()
    const [isRenameDialogOpen, setIsRenameDialogOpen] = useState(false)

    const handleRename = () => {
        if (session) {
            setIsRenameDialogOpen(true)
        }
    }

    return (
        <>
            <DropdownMenu>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <DropdownMenuTrigger
                            aria-label={t('tooltips.moreOptions')}
                            className={clsx(
                                'cursor-pointer',
                                triggerClassName
                            )}
                        >
                            <Icon
                                name="more"
                                className="size-6 fill-black dark:fill-white"
                            />
                        </DropdownMenuTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="end">
                        {t('tooltips.moreOptions')}
                    </TooltipContent>
                </Tooltip>
                <DropdownMenuContent
                    align="end"
                    className="w-[185px] px-4 py-2"
                >
                    <DropdownMenuItem className="py-2" onClick={onShare}>
                        <Icon name="share" className="size-5 stroke-black" />
                        {t('common.share')}
                    </DropdownMenuItem>
                    {session && (
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
                    )}
                    <DropdownMenuItem
                        className="py-2"
                        onClick={onToggleFavorite}
                    >
                        {isFavorite ? (
                            <Icon
                                name="star-fill"
                                className="fill-black size-5"
                            />
                        ) : (
                            <Icon name="star" className="fill-black size-5" />
                        )}
                        {isFavorite
                            ? t('dashboard.unfavorite')
                            : t('dashboard.favorite')}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="my-1" />
                    <DropdownMenuItem
                        onClick={onDelete}
                        variant="destructive"
                        className="text-red-2 py-2"
                    >
                        <Icon name="trash" className="size-5" />
                        {t('common.delete')}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
            {session && (
                <RenameSessionDialog
                    session={session}
                    open={isRenameDialogOpen}
                    onOpenChange={setIsRenameDialogOpen}
                />
            )}
        </>
    )
}

export default HeaderDropdownMenu
