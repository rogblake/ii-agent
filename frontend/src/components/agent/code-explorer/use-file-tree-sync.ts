import { useEffect, useRef } from 'react'
import {
    useAppDispatch,
    useAppSelector,
    selectIsTreeLoading,
    selectWsConnectionState,
    setTreeLoading
} from '@/state'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { CommandType, WebSocketConnectionState } from '@/typings/agent'

/**
 * Encapsulates file-tree loading and manual refresh.
 *
 * Live updates arrive through `file_tree_update` events emitted by the agent
 * loop, so the explorer no longer needs to start or stop a dedicated watcher.
 */
export function useFileTreeSync(sessionId: string | undefined) {
    const dispatch = useAppDispatch()
    const { sendMessage, isSessionReady } = useSocketIOContext()

    const isTreeLoading = useAppSelector(selectIsTreeLoading)
    const wsConnectionState = useAppSelector(selectWsConnectionState)

    const hasRequestedTree = useRef(false)

    const isSocketConnected =
        wsConnectionState === WebSocketConnectionState.CONNECTED

    useEffect(() => {
        hasRequestedTree.current = false
    }, [sessionId])

    useEffect(() => {
        if (!isSocketConnected) {
            hasRequestedTree.current = false
        }
    }, [isSocketConnected])

    useEffect(() => {
        if (
            isSocketConnected &&
            isSessionReady &&
            !isTreeLoading &&
            !hasRequestedTree.current
        ) {
            hasRequestedTree.current = true
            dispatch(setTreeLoading(true))
            const sent = sendMessage({ session_uuid: '', content: { command: CommandType.FILE_TREE } })
            if (!sent) {
                hasRequestedTree.current = false
                dispatch(setTreeLoading(false))
            }
        }
    }, [
        dispatch,
        isSocketConnected,
        isSessionReady,
        isTreeLoading,
        sendMessage
    ])

    function requestTreeRefresh() {
        if (!isSessionReady) {
            return
        }
        hasRequestedTree.current = true
        dispatch(setTreeLoading(true))
        const sent = sendMessage({ session_uuid: '', content: { command: CommandType.FILE_TREE } })
        if (!sent) {
            hasRequestedTree.current = false
            dispatch(setTreeLoading(false))
        }
    }

    return { requestTreeRefresh }
}
