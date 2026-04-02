import { cn } from '@/lib/utils'
import { Icon } from '../../ui/icon'
import { VIDEO_TEMPLATES, type VideoTemplate } from '@/constants/video-models'

interface VideoTemplatesSectionProps {
    onTemplateSelect: (template: VideoTemplate) => void
    onAddTemplate?: () => void
    className?: string
}

interface TemplateCardProps {
    template: VideoTemplate
    onClick: () => void
}

const TemplateCard = ({ template, onClick }: TemplateCardProps) => (
    <button
        type="button"
        onClick={onClick}
        className="relative h-[140px] w-[164px] rounded-[12px] overflow-hidden group cursor-pointer flex-shrink-0"
    >
        {/* Thumbnail */}
        <img
            src={template.thumbnail}
            alt={template.name}
            className="absolute inset-0 w-full h-full object-cover"
        />

        {/* Gradient overlay - matching Figma exactly */}
        <div
            className={cn(
                'absolute bottom-0 left-0 right-0 h-[100px]',
                'bg-gradient-to-t from-[#082323] to-[rgba(166,255,255,0)]',
                'rounded-b-[12px]'
            )}
        />

        {/* Template info - positioned at bottom left */}
        <div className="absolute bottom-[8px] left-[12px] flex items-center gap-[6px]">
            <Icon name="video-ai" className="size-5 fill-white" />
            <span className="text-[12px] font-normal text-white font-['Satoshi',sans-serif]">
                {template.name}
            </span>
        </div>

        {/* Hover overlay */}
        <div
            className={cn(
                'absolute inset-0 bg-[#a6ffff]/10 opacity-0',
                'group-hover:opacity-100 transition-opacity',
                'border-2 border-transparent group-hover:border-[#a6ffff]',
                'rounded-[12px]'
            )}
        />
    </button>
)

const AddTemplateCard = ({ onClick }: { onClick?: () => void }) => (
    <button
        type="button"
        onClick={onClick}
        className={cn(
            'h-[48px] w-[48px] rounded-full flex-shrink-0',
            'bg-transparent',
            'flex items-center justify-center',
            'hover:bg-[#a6ffff]/10 transition-colors',
            'cursor-pointer'
        )}
    >
        <Icon name="add-circle" className="size-6 fill-[#a6ffff]" />
    </button>
)

export const VideoTemplatesSection = ({
    onTemplateSelect,
    onAddTemplate,
    className
}: VideoTemplatesSectionProps) => {
    return (
        <div className={cn('w-full', className)}>
            {/* Header - matching Figma: 14px bold white */}
            <p className="text-[14px] font-bold text-white font-['Satoshi',sans-serif] mb-4 px-6">
                Pick a video template for your ideas
            </p>

            {/* Templates row - matching Figma layout with 16px gap */}
            <div className="flex items-center gap-[16px] px-6 overflow-x-auto pb-2">
                {VIDEO_TEMPLATES.map((template) => (
                    <TemplateCard
                        key={template.id}
                        template={template}
                        onClick={() => onTemplateSelect(template)}
                    />
                ))}

                {/* Add template button - centered vertically within the row */}
                <div className="flex items-center justify-center h-[140px]">
                    <AddTemplateCard onClick={onAddTemplate} />
                </div>
            </div>
        </div>
    )
}

export default VideoTemplatesSection
