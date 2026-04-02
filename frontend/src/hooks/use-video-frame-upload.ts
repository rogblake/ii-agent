import { useState, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import store from '@/state/store'
import {
    selectChatMediaPreference,
    setChatMediaPreference,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { useUploadFiles } from './use-upload-files'

export function useVideoFrameUpload() {
    const dispatch = useAppDispatch()
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)
    const { uploadFileWithSignedUrl } = useUploadFiles()
    const [uploadingFrames, setUploadingFrames] = useState<Set<'start' | 'end'>>(new Set())

    const addFrame = useCallback(async (file: File, type: 'start' | 'end') => {
        const frameId = uuidv4()

        setUploadingFrames(prev => new Set(prev).add(type))

        try {
            const uploadResult = await uploadFileWithSignedUrl(file)

            if (uploadResult) {
                // Get CURRENT state at dispatch time to avoid stale closure
                const currentState = store.getState()
                const currentPreference = selectChatMediaPreference(currentState)
                const currentFrames = currentPreference.video_frames ?? []

                dispatch(
                    setChatMediaPreference({
                        ...currentPreference,
                        video_frames: [
                            ...currentFrames.filter(f => f.type !== type),
                            {
                                id: frameId,
                                url: uploadResult.fileUrl,
                                type,
                                file_id: uploadResult.fileId
                            }
                        ]
                    })
                )
            } else {
                console.error('Failed to upload video frame')
            }
        } catch (error) {
            console.error('Failed to upload video frame:', error)
        } finally {
            setUploadingFrames(prev => {
                const next = new Set(prev)
                next.delete(type)
                return next
            })
        }
    }, [dispatch, uploadFileWithSignedUrl])

    const removeFrame = useCallback((frameId: string) => {
        const frame = chatMediaPreference.video_frames?.find(f => f.id === frameId)
        if (frame?.url.startsWith('blob:')) {
            URL.revokeObjectURL(frame.url)
        }

        const currentFrames = chatMediaPreference.video_frames ?? []
        dispatch(
            setChatMediaPreference({
                ...chatMediaPreference,
                video_frames: currentFrames.filter(f => f.id !== frameId)
            })
        )
    }, [chatMediaPreference, dispatch])

    return {
        uploadingFrames,
        isUploading: uploadingFrames.size > 0,
        addFrame,
        removeFrame
    }
}
