import {
    CopyIcon,
    RefreshCcwIcon,
    ShareIcon,
    ThumbsDownIcon,
    ThumbsUpIcon
} from 'lucide-react'
import { Action, Actions } from './ai-elements/actions'
import { useTranslation } from 'react-i18next'

const PostAction = () => {
    const { t } = useTranslation()
    const handleRetry = () => {}
    const handleCopy = () => {}
    const handleShare = () => {}
    const handleLike = () => {}
    const handleDislike = () => {}

    const actions = [
        {
            icon: RefreshCcwIcon,
            label: t('common.retry'),
            onClick: () => handleRetry()
        },
        {
            icon: ThumbsUpIcon,
            label: t('feedback.like'),
            onClick: () => handleLike()
        },
        {
            icon: ThumbsDownIcon,
            label: t('feedback.dislike'),
            onClick: () => handleDislike()
        },
        {
            icon: CopyIcon,
            label: t('common.copy'),
            onClick: () => handleCopy()
        },
        {
            icon: ShareIcon,
            label: t('common.share'),
            onClick: () => handleShare()
        }
    ]

    return (
        <Actions className="mt-2 -ml-2">
            {actions.map((action) => (
                <Action key={action.label} label={action.label}>
                    <action.icon className="size-4" />
                </Action>
            ))}
        </Actions>
    )
}

export default PostAction
