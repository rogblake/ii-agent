import { useIsMobile } from '@/hooks/use-mobile'
import { Icon } from '../../ui/icon'
import { useSidebar } from '../../ui/sidebar'
import type { AdvancedModeData } from './advanced-mode-modal'
import { useTranslation } from 'react-i18next'

type Props = {
    data: AdvancedModeData | null
    onEdit: () => void
    className?: string
    /** When true, skip inline style positioning (used when rendered via portal) */
    usePortal?: boolean
}

const categoryConfig = [
    { key: 'subject' as const, icon: 'user', titleKey: 'subject' },
    { key: 'scene' as const, icon: 'scene', titleKey: 'scene' },
    { key: 'style' as const, icon: 'magic-pen', titleKey: 'style' }
]

export const AdvancedModePreview = ({
    data,
    onEdit,
    className = '',
    usePortal = false
}: Props) => {
    const { t } = useTranslation()
    const { state } = useSidebar()
    const isExpanded = state === 'expanded'
    const isMobile = useIsMobile()

    const getStyle = () => {
        if (usePortal) return undefined
        if (isMobile) {
            return {
                position: 'fixed' as const,
                left: 'auto',
                right: '24px',
                top: 'auto',
                bottom: '196px'
            }
        }
        return { left: isExpanded ? 'calc(17rem)' : 'calc(1rem)' }
    }

    return (
        <button
            onClick={onEdit}
            className={
                usePortal
                    ? `z-20 flex flex-row gap-2 p-[6px] rounded-lg transition-all duration-200 bg-white dark:bg-[#263533] border border-[#d7dde2] dark:border-transparent shadow-md cursor-pointer hover:shadow-lg ${className}`
                    : `relative md:fixed top-1/2 translate-y-0 md:-translate-y-1/2 z-20 flex flex-row md:flex-col gap-2 md:gap-3 p-[6px] md:p-3 rounded-lg md:rounded-2xl transition-all duration-200 bg-white dark:bg-[#263533] border border-[#d7dde2] dark:border-transparent shadow-md cursor-pointer hover:shadow-lg ${className}`
            }
            style={getStyle()}
            title={t('media.advancedMode.editTitle')}
        >
            {categoryConfig.map((cat) => {
                const categoryData = data?.[cat.key]
                const images = categoryData?.images || []
                const firstImage = images[0]
                const imageCount = images.length
                const categoryTitle = t(
                    `media.advancedMode.categories.${cat.titleKey}.title`
                )

                return (
                    <div key={cat.key} className="relative">
                        <div className="size-9 md:size-12 rounded-lg md:rounded-xl overflow-hidden flex items-center justify-center bg-[#d7dde2] dark:bg-[#677170] transition-colors">
                            {firstImage?.preview ? (
                                <img
                                    src={firstImage.preview}
                                    alt={categoryTitle}
                                    className="w-full h-full object-cover"
                                />
                            ) : (
                                <Icon
                                    name={cat.icon}
                                    className="size-6 text-black dark:text-white fill-black dark:fill-white"
                                />
                            )}
                        </div>
                        {imageCount > 1 && (
                            <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-[#f5425f] text-white text-xs font-bold flex items-center justify-center">
                                {imageCount}
                            </div>
                        )}
                    </div>
                )
            })}
        </button>
    )
}
