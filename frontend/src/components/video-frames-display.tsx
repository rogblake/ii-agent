import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { chatService } from '@/services/chat.service'
import type { VideoFrameReference } from '@/typings/agent'

/** Renders a frame thumbnail, fetching HEIC through the backend for JPEG conversion. */
const FrameImage = ({ frame }: { frame: VideoFrameReference }) => {
    const [src, setSrc] = useState(frame.url)
    useEffect(() => {
        const isHeic = /\.(heic|heif)$/i.test(frame.url?.split('?')[0] ?? '')
        if (!isHeic || !frame.file_id) return
        let cancelled = false
        let blobUrl = ''
        chatService
            .getFileContent({ fileId: frame.file_id })
            .then((blob) => {
                if (cancelled) return
                blobUrl = URL.createObjectURL(blob)
                setSrc(blobUrl)
            })
            .catch(() => {})
        return () => { cancelled = true; if (blobUrl) URL.revokeObjectURL(blobUrl) }
    }, [frame.url, frame.file_id])
    return (
        <img src={src} alt={`${frame.type} frame`} className="w-full h-full object-cover" />
    )
}

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
                        <FrameImage frame={frame} />
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
