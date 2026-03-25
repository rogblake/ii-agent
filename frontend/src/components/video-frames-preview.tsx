import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Icon } from './ui/icon'
import { chatService } from '@/services/chat.service'
import type { VideoFrameReference } from '@/typings/agent'

/** Renders a frame thumbnail, fetching HEIC through the backend for JPEG conversion. */
const HeicSafeImg = ({ frame }: { frame: VideoFrameReference }) => {
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

interface VideoFramesPreviewProps {
    frames: VideoFrameReference[]
    uploadingTypes: Set<'start' | 'end'>
    className?: string
    onRemove: (frameId: string) => void
}

const VideoFramesPreview = ({
    frames,
    uploadingTypes,
    className = '',
    onRemove
}: VideoFramesPreviewProps) => {
    if (frames.length === 0 && uploadingTypes.size === 0) return null

    return (
        <div className={`flex items-center gap-2 ${className}`}>
            {frames.map((frame) => {
                const isUploading = uploadingTypes.has(frame.type)

                return (
                    <div key={frame.id} className="relative group">
                        <div className="size-12 rounded-lg overflow-hidden border border-white/20">
                            <HeicSafeImg frame={frame} />
                        </div>

                        {/* Loading overlay */}
                        {isUploading && (
                            <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
                                <Loader2 className="size-5 text-white animate-spin" />
                            </div>
                        )}

                        {/* Remove button */}
                        <button
                            onClick={() => onRemove(frame.id)}
                            disabled={isUploading}
                            className="absolute -right-1 -top-1 cursor-pointer rounded-full bg-red-2 transition-colors disabled:opacity-50"
                        >
                            <Icon
                                name="close"
                                className="size-4 fill-white p-0.5"
                            />
                        </button>
                    </div>
                )
            })}
        </div>
    )
}

export default VideoFramesPreview
