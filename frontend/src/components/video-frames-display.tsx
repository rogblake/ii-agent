import { useTranslation } from 'react-i18next'
import type { VideoFrameReference } from '@/typings/agent'

interface VideoFramesDisplayProps {
    frames?: VideoFrameReference[]
    className?: string
}

export function VideoFramesDisplay({
    frames,
    className = ''
}: VideoFramesDisplayProps): React.ReactElement | null {
    const { t } = useTranslation()

    if (!frames || frames.length === 0) {
        return null
    }

    return (
        <div
            className={`flex flex-wrap items-center gap-2 justify-end ${className}`}
        >
            {frames.map((frame) => (
                <div
                    key={frame.id}
                    className="relative inline-block rounded-xl overflow-hidden"
                >
                    <div className="w-24 h-16 rounded-xl overflow-hidden border border-white/20">
                        <img
                            src={frame.url}
                            alt={`${frame.type} frame`}
                            className="w-full h-full object-cover"
                        />
                    </div>
                    <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs px-1 py-0.5 text-center">
                        {frame.type === 'start'
                            ? t('media.videoFrames.startLabel')
                            : t('media.videoFrames.endLabel')}
                    </div>
                </div>
            ))}
        </div>
    )
}
