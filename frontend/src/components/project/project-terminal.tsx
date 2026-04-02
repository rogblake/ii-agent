'use client'

import { FitAddon } from '@xterm/addon-fit'
import { Terminal as XTerm } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useTheme } from 'next-themes'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { useSocketIOContext } from '@/contexts/websocket-context'

type TerminalStatus = 'waiting' | 'connecting' | 'ready' | 'closed' | 'error'

interface ProjectTerminalProps {
    sessionId?: string
}

function buildTerminalId() {
    return (
        globalThis.crypto?.randomUUID?.() ??
        `${Date.now()}-${Math.random().toString(16).slice(2)}`
    )
}

function getThemeOptions(theme: string | undefined) {
    const isDark = theme === 'dark'
    return {
        background: isDark ? 'rgba(17, 24, 39, 0.96)' : 'rgba(248, 250, 252, 1)',
        foreground: isDark ? '#e5eefb' : '#172033',
        cursor: isDark ? '#7dd3fc' : '#111827',
        cursorAccent: isDark ? '#111827' : '#f8fafc',
        selectionBackground: isDark
            ? 'rgba(125, 211, 252, 0.22)'
            : 'rgba(17, 24, 39, 0.16)',
        selectionForeground: undefined,
        black: isDark ? '#1f2937' : '#1f2937',
        red: isDark ? '#f87171' : '#b91c1c',
        green: isDark ? '#4ade80' : '#15803d',
        yellow: isDark ? '#facc15' : '#a16207',
        blue: isDark ? '#60a5fa' : '#1d4ed8',
        magenta: isDark ? '#c084fc' : '#7e22ce',
        cyan: isDark ? '#22d3ee' : '#0f766e',
        white: isDark ? '#e5e7eb' : '#d1d5db',
        brightBlack: isDark ? '#6b7280' : '#4b5563',
        brightRed: isDark ? '#fca5a5' : '#dc2626',
        brightGreen: isDark ? '#86efac' : '#16a34a',
        brightYellow: isDark ? '#fde047' : '#ca8a04',
        brightBlue: isDark ? '#93c5fd' : '#2563eb',
        brightMagenta: isDark ? '#d8b4fe' : '#9333ea',
        brightCyan: isDark ? '#67e8f9' : '#0891b2',
        brightWhite: isDark ? '#f9fafb' : '#111827'
    }
}

const ProjectTerminal = ({ sessionId }: ProjectTerminalProps) => {
    const { theme } = useTheme()
    const { t } = useTranslation()
    const { socket, isSessionReady } = useSocketIOContext()

    const containerRef = useRef<HTMLDivElement | null>(null)
    const termRef = useRef<XTerm | null>(null)
    const fitAddonRef = useRef<FitAddon | null>(null)
    const terminalIdRef = useRef<string | null>(null)
    const socketRef = useRef(socket)
    const statusRef = useRef<TerminalStatus>('waiting')
    const resizeObserverRef = useRef<ResizeObserver | null>(null)
    const [isTerminalMounted, setIsTerminalMounted] = useState(false)
    const [status, setStatus] = useState<TerminalStatus>('waiting')

    socketRef.current = socket
    statusRef.current = status

    const emitResize = () => {
        const term = termRef.current
        const terminalId = terminalIdRef.current
        const activeSocket = socketRef.current
        if (!term || !terminalId || !activeSocket?.connected) {
            return
        }
        activeSocket.emit('pty_resize', {
            terminal_id: terminalId,
            cols: term.cols,
            rows: term.rows
        })
    }

    const startTerminal = (resetTerminal: boolean) => {
        const activeSocket = socketRef.current
        const term = termRef.current
        const fitAddon = fitAddonRef.current

        if (!sessionId || !isSessionReady || !activeSocket?.connected || !term || !fitAddon) {
            return
        }

        const terminalId = buildTerminalId()
        terminalIdRef.current = terminalId
        setStatus('connecting')

        if (resetTerminal) {
            term.reset()
        }

        fitAddon.fit()
        term.focus()
        activeSocket.emit('pty_create', {
            terminal_id: terminalId,
            cols: term.cols,
            rows: term.rows
        })
    }

    useEffect(() => {
        const container = containerRef.current
        if (!container || termRef.current) {
            return
        }

        const term = new XTerm({
            cursorBlink: true,
            fontSize: 13,
            lineHeight: 1.25,
            fontFamily:
                '"JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, monospace',
            theme: getThemeOptions(theme),
            allowTransparency: true,
            convertEol: false,
            scrollback: 5000
        })
        const fitAddon = new FitAddon()
        term.loadAddon(fitAddon)
        term.open(container)
        fitAddon.fit()

        const inputDisposable = term.onData((data) => {
            const activeSocket = socketRef.current
            const terminalId = terminalIdRef.current
            if (
                !activeSocket?.connected ||
                !terminalId ||
                statusRef.current !== 'ready'
            ) {
                return
            }
            activeSocket.emit('pty_input', {
                terminal_id: terminalId,
                data
            })
        })

        const observer = new ResizeObserver(() => {
            fitAddon.fit()
            emitResize()
        })
        observer.observe(container)

        termRef.current = term
        fitAddonRef.current = fitAddon
        resizeObserverRef.current = observer
        setIsTerminalMounted(true)

        return () => {
            observer.disconnect()
            inputDisposable.dispose()
            term.dispose()
            resizeObserverRef.current = null
            fitAddonRef.current = null
            termRef.current = null
            setIsTerminalMounted(false)
        }
    }, [])

    useEffect(() => {
        if (!termRef.current) {
            return
        }
        termRef.current.options.theme = getThemeOptions(theme)
    }, [theme])

    useEffect(() => {
        const activeSocket = socket
        if (!activeSocket) {
            return
        }

        const handleReady = (payload: {
            terminal_id?: string
            cols?: number
            rows?: number
        }) => {
            if (payload.terminal_id !== terminalIdRef.current) {
                return
            }
            setStatus('ready')
            if (typeof payload.cols === 'number' && typeof payload.rows === 'number') {
                emitResize()
            }
        }

        const handleOutput = (payload: {
            terminal_id?: string
            data?: string
        }) => {
            if (payload.terminal_id !== terminalIdRef.current || !payload.data) {
                return
            }
            if (statusRef.current === 'waiting' || statusRef.current === 'connecting') {
                setStatus('ready')
            }
            termRef.current?.write(payload.data)
        }

        const handleError = (payload: {
            terminal_id?: string
            message?: string
        }) => {
            if (
                payload.terminal_id &&
                payload.terminal_id !== terminalIdRef.current
            ) {
                return
            }
            const message =
                payload.message || t('project.terminal.errors.unableToStart')
            setStatus('error')
            termRef.current?.writeln(`\r\n${message}`)
            toast.error(message)
        }

        const handleClosed = (payload: {
            terminal_id?: string
            exit_code?: number
        }) => {
            if (payload.terminal_id !== terminalIdRef.current) {
                return
            }
            const exitSuffix =
                typeof payload.exit_code === 'number'
                    ? ` (${t('project.terminal.status.exitCode', {
                          code: payload.exit_code
                      })})`
                    : ''
            termRef.current?.writeln(
                `\r\n${t('project.terminal.status.closed')}${exitSuffix}`
            )
            setStatus('closed')
        }

        activeSocket.on('pty_ready', handleReady)
        activeSocket.on('pty_output', handleOutput)
        activeSocket.on('pty_error', handleError)
        activeSocket.on('pty_closed', handleClosed)

        return () => {
            activeSocket.off('pty_ready', handleReady)
            activeSocket.off('pty_output', handleOutput)
            activeSocket.off('pty_error', handleError)
            activeSocket.off('pty_closed', handleClosed)
        }
    }, [socket, t])

    useEffect(() => {
        if (!sessionId) {
            setStatus('error')
            return
        }

        if (!isSessionReady || !isTerminalMounted) {
            setStatus('waiting')
            terminalIdRef.current = null
            return
        }

        startTerminal(true)

        return () => {
            const activeSocket = socketRef.current
            const terminalId = terminalIdRef.current
            if (activeSocket?.connected && terminalId) {
                activeSocket.emit('pty_close', { terminal_id: terminalId })
            }
            terminalIdRef.current = null
        }
    }, [isSessionReady, isTerminalMounted, sessionId])

    const handleRestart = () => {
        startTerminal(true)
    }

    const statusLabelKey =
        status === 'ready'
            ? 'project.terminal.status.ready'
            : status === 'connecting'
              ? 'project.terminal.status.connecting'
              : status === 'closed'
                ? 'project.terminal.status.closed'
                : status === 'error'
                  ? 'project.terminal.status.error'
                  : 'project.terminal.status.waiting'

    return (
        <div className="flex h-[calc(100vh-280px)] flex-col overflow-hidden rounded-lg border border-border bg-background dark:bg-black/15">
            <div className="flex items-center justify-between border-b border-border px-3 py-2 dark:border-white/10">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                    {t(statusLabelKey)}
                </p>
                <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleRestart}
                    disabled={!isSessionReady || !isTerminalMounted}
                >
                    {t('project.terminal.actions.restart')}
                </Button>
            </div>
            <div className="min-h-0 flex-1 bg-slate-50 dark:bg-slate-950">
                <div ref={containerRef} className="h-full w-full px-2 py-1" />
            </div>
        </div>
    )
}

export default ProjectTerminal
