import { useEffect, useRef, useState } from 'react'
import {
    CheckIcon,
    CopyIcon,
    ExternalLinkIcon,
    ImageOffIcon,
    Loader2Icon
} from 'lucide-react'
import type { Element, ElementContent } from 'hast'
import { useTheme } from 'next-themes'
import { codeToHtml, type BundledLanguage } from 'shiki'

import axios from '@/lib/axios'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { selectVscodeUrl, useAppSelector } from '@/state'
import type { OpenFile } from '@/state/slice/file-explorer'

const SHIKI_LANGUAGES = new Set([
    'javascript',
    'typescript',
    'jsx',
    'tsx',
    'python',
    'html',
    'css',
    'scss',
    'json',
    'markdown',
    'yaml',
    'toml',
    'sql',
    'bash',
    'rust',
    'go',
    'java',
    'ruby',
    'php',
    'swift',
    'kotlin',
    'c',
    'cpp',
    'xml',
    'graphql',
    'prisma',
    'dockerfile',
    'makefile',
    'plaintext'
])

const LINE_NUMBER_TRANSFORMER = {
    name: 'line-numbers',
    line(node: Element, line: number) {
        const lineNumberNode: ElementContent = {
            type: 'element',
            tagName: 'span',
            properties: {
                className: [
                    'inline-block',
                    'min-w-[3rem]',
                    'pr-4',
                    'text-right',
                    'select-none',
                    'opacity-30'
                ]
            },
            children: [{ type: 'text', value: String(line) }]
        }

        node.children.unshift(lineNumberNode)
    }
}

function getShikiLang(language: string): BundledLanguage {
    if (SHIKI_LANGUAGES.has(language)) return language as BundledLanguage
    return 'plaintext' as BundledLanguage
}

function getFileLabel(path: string): string {
    return path.split('/').filter(Boolean).pop() || path
}

function buildSvgPreviewUrl(content: string, mimeType: string): string {
    return URL.createObjectURL(new Blob([content], { type: mimeType }))
}

type CachedImagePreview = {
    sessionId: string
    path: string
    revision: number
    url: string
    size: number
}

type PreviewUrlOwner = 'cache' | 'ephemeral' | null

const IMAGE_PREVIEW_CACHE_MAX_ENTRIES = 12
const IMAGE_PREVIEW_CACHE_MAX_BYTES = 64 * 1024 * 1024

const imagePreviewCache = new Map<string, CachedImagePreview>()
let imagePreviewCacheBytes = 0

function getImagePreviewCacheKey(
    sessionId: string,
    path: string,
    revision: number
): string {
    return `${sessionId}:${revision}:${path}`
}

function removeCachedImagePreview(key: string): void {
    const entry = imagePreviewCache.get(key)
    if (!entry) return

    imagePreviewCache.delete(key)
    imagePreviewCacheBytes -= entry.size
    URL.revokeObjectURL(entry.url)
}

function getCachedImagePreview(key: string): CachedImagePreview | null {
    const entry = imagePreviewCache.get(key)
    if (!entry) return null

    imagePreviewCache.delete(key)
    imagePreviewCache.set(key, entry)
    return entry
}

function pruneStaleImagePreviewRevisions(
    sessionId: string,
    path: string,
    retainKey: string
): void {
    for (const [key, entry] of imagePreviewCache.entries()) {
        if (
            key !== retainKey &&
            entry.sessionId === sessionId &&
            entry.path === path
        ) {
            removeCachedImagePreview(key)
        }
    }
}

function evictCachedImagePreviews(): void {
    while (
        imagePreviewCache.size > IMAGE_PREVIEW_CACHE_MAX_ENTRIES ||
        imagePreviewCacheBytes > IMAGE_PREVIEW_CACHE_MAX_BYTES
    ) {
        const oldestKey = imagePreviewCache.keys().next().value
        if (!oldestKey) return
        removeCachedImagePreview(oldestKey)
    }
}

function cacheImagePreview(entry: CachedImagePreview): boolean {
    if (entry.size > IMAGE_PREVIEW_CACHE_MAX_BYTES) {
        return false
    }

    const key = getImagePreviewCacheKey(
        entry.sessionId,
        entry.path,
        entry.revision
    )

    pruneStaleImagePreviewRevisions(entry.sessionId, entry.path, key)
    removeCachedImagePreview(key)

    imagePreviewCache.set(key, entry)
    imagePreviewCacheBytes += entry.size
    evictCachedImagePreviews()

    return imagePreviewCache.has(key)
}

interface CodeViewerProps {
    file: OpenFile
    sessionId?: string
    className?: string
}

export function CodeViewer({
    file,
    sessionId,
    className
}: CodeViewerProps) {
    const { resolvedTheme } = useTheme()
    const vscodeUrl = useAppSelector(selectVscodeUrl)
    const isDark = resolvedTheme === 'dark'
    const [html, setHtml] = useState('')
    const [copied, setCopied] = useState(false)
    const [svgMode, setSvgMode] = useState<'preview' | 'source'>('preview')
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [previewError, setPreviewError] = useState<string | null>(null)
    const renderKey = useRef(0)
    const previewOwnerRef = useRef<PreviewUrlOwner>(null)
    const previewUrlRef = useRef<string | null>(null)

    const isTextFile = file.kind === 'text'
    const isSvgFile = file.kind === 'svg'
    const shouldRenderSource = isTextFile || (isSvgFile && svgMode === 'source')
    const canCopy = isTextFile || (isSvgFile && svgMode === 'source')

    const setPreviewResource = (
        nextUrl: string | null,
        owner: PreviewUrlOwner
    ) => {
        const currentUrl = previewUrlRef.current

        if (
            currentUrl &&
            currentUrl !== nextUrl &&
            previewOwnerRef.current === 'ephemeral'
        ) {
            URL.revokeObjectURL(currentUrl)
        }

        previewOwnerRef.current = nextUrl ? owner : null
        previewUrlRef.current = nextUrl
        setPreviewUrl(nextUrl)
    }

    useEffect(() => {
        if (file.kind === 'svg') {
            setSvgMode('preview')
        }
    }, [file.kind, file.path])

    useEffect(() => {
        const key = ++renderKey.current

        if (file.kind !== 'text' && file.kind !== 'svg') {
            setHtml('')
            return
        }

        if (file.kind === 'svg' && svgMode !== 'source') {
            setHtml('')
            return
        }

        const source = file.content
        const lang = getShikiLang(file.language)
        const theme = isDark ? 'one-dark-pro' : 'one-light'

        codeToHtml(source, {
            lang,
            theme,
            transformers: [LINE_NUMBER_TRANSFORMER]
        }).then((result) => {
            if (renderKey.current === key) {
                setHtml(result)
            }
        })
    }, [file, isDark, svgMode])

    useEffect(() => {
        let isActive = true

        if (file.kind === 'svg') {
            setPreviewLoading(false)
            setPreviewError(null)
            setPreviewResource(
                buildSvgPreviewUrl(file.content, file.mimeType),
                'ephemeral'
            )
            return
        }

        if (file.kind !== 'image') {
            setPreviewLoading(false)
            setPreviewError(null)
            setPreviewResource(null, null)
            return
        }

        if (!sessionId) {
            setPreviewLoading(false)
            setPreviewError('Image preview is unavailable for this session.')
            setPreviewResource(null, null)
            return
        }

        const cacheKey = getImagePreviewCacheKey(
            sessionId,
            file.path,
            file.revision
        )
        const cachedPreview = getCachedImagePreview(cacheKey)

        if (cachedPreview) {
            setPreviewLoading(false)
            setPreviewError(null)
            setPreviewResource(cachedPreview.url, 'cache')
            return
        }

        setPreviewLoading(true)
        setPreviewError(null)

        axios
            .get(`/sandbox-files/${sessionId}/preview`, {
                params: { path: file.path },
                responseType: 'blob'
            })
            .then((response) => {
                if (!isActive) return

                const previewObjectUrl = URL.createObjectURL(response.data)
                const cached = cacheImagePreview({
                    sessionId,
                    path: file.path,
                    revision: file.revision,
                    url: previewObjectUrl,
                    size: response.data.size
                })

                setPreviewResource(
                    previewObjectUrl,
                    cached ? 'cache' : 'ephemeral'
                )
            })
            .catch(() => {
                if (!isActive) return
                setPreviewError('Could not load image preview.')
                setPreviewResource(null, null)
            })
            .finally(() => {
                if (isActive) {
                    setPreviewLoading(false)
                }
            })

        return () => {
            isActive = false
        }
    }, [
        file,
        file.kind === 'image' ? file.revision : undefined,
        sessionId
    ])

    useEffect(() => {
        return () => {
            if (
                previewUrlRef.current &&
                previewOwnerRef.current === 'ephemeral'
            ) {
                URL.revokeObjectURL(previewUrlRef.current)
            }
        }
    }, [])

    const handleCopy = async () => {
        if (!canCopy) return

        const content = file.kind === 'text' || file.kind === 'svg' ? file.content : ''
        await navigator.clipboard.writeText(content)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    const handleOpenVSCode = () => {
        if (!vscodeUrl) return
        window.open(vscodeUrl, '_blank')
    }

    return (
        <div className={cn('flex h-full flex-col bg-background text-foreground', className)}>
            <div className="flex items-center justify-between gap-3 border-b border-border bg-muted/40 px-4 py-2 dark:border-white/10 dark:bg-black/20">
                <div className="flex items-center gap-1.5 overflow-hidden text-xs text-muted-foreground">
                    {file.path
                        .split('/')
                        .filter(Boolean)
                        .map((part, i, arr) => (
                            <span key={i} className="flex items-center gap-1.5">
                                {i > 0 && (
                                    <span className="text-muted-foreground/60">
                                        /
                                    </span>
                                )}
                                <span
                                    className={cn(
                                        'truncate',
                                        i === arr.length - 1
                                            ? 'font-medium text-firefly dark:text-sky-blue'
                                            : 'text-muted-foreground'
                                    )}
                                >
                                    {part}
                                </span>
                            </span>
                        ))}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                    {isSvgFile && (
                        <div className="flex items-center gap-1 rounded-md border border-border bg-background/80 p-1 dark:border-white/10 dark:bg-white/5">
                            <button
                                className={cn(
                                    'rounded px-2 py-1 text-[11px] font-medium transition-colors cursor-pointer',
                                    svgMode === 'preview'
                                        ? 'bg-sky-blue text-charcoal'
                                        : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground dark:hover:bg-white/5 dark:hover:text-white'
                                )}
                                onClick={() => setSvgMode('preview')}
                            >
                                Preview
                            </button>
                            <button
                                className={cn(
                                    'rounded px-2 py-1 text-[11px] font-medium transition-colors cursor-pointer',
                                    svgMode === 'source'
                                        ? 'bg-sky-blue text-charcoal'
                                        : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground dark:hover:bg-white/5 dark:hover:text-white'
                                )}
                                onClick={() => setSvgMode('source')}
                            >
                                Source
                            </button>
                        </div>
                    )}

                    {(file.kind === 'binary' || file.kind === 'image') && (
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={handleOpenVSCode}
                            disabled={!vscodeUrl}
                        >
                            <ExternalLinkIcon size={12} />
                            Open VS Code
                        </Button>
                    )}

                    {canCopy && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 text-muted-foreground hover:bg-accent hover:text-foreground dark:hover:bg-white/10 dark:hover:text-white"
                            onClick={handleCopy}
                        >
                            {copied ? (
                                <CheckIcon size={14} />
                            ) : (
                                <CopyIcon size={14} />
                            )}
                        </Button>
                    )}
                </div>
            </div>

            <div className="flex-1 overflow-auto">
                {file.kind === 'binary' && (
                    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
                        <div className="rounded-full border border-border bg-muted p-4 dark:border-white/10 dark:bg-firefly/50">
                            <ImageOffIcon
                                size={24}
                                className="text-muted-foreground"
                            />
                        </div>
                        <div className="space-y-1">
                            <p className="text-sm font-medium text-foreground">
                                {getFileLabel(file.path)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                {file.message}
                            </p>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            className="text-xs"
                            onClick={handleOpenVSCode}
                            disabled={!vscodeUrl}
                        >
                            <ExternalLinkIcon size={12} />
                            Open VS Code
                        </Button>
                    </div>
                )}

                {(file.kind === 'image' ||
                    (file.kind === 'svg' && svgMode === 'preview')) && (
                    <div className="flex h-full items-center justify-center bg-muted/40 p-4 dark:bg-black/20">
                        {previewLoading && (
                            <Loader2Icon
                                size={22}
                                className="animate-spin text-firefly dark:text-sky-blue"
                            />
                        )}
                        {!previewLoading && previewError && (
                            <div className="text-center">
                                <p className="mb-1 text-sm text-foreground">
                                    {getFileLabel(file.path)}
                                </p>
                                <p className="text-xs text-red">
                                    {previewError}
                                </p>
                            </div>
                        )}
                        {!previewLoading && !previewError && previewUrl && (
                            <img
                                src={previewUrl}
                                alt={getFileLabel(file.path)}
                                className="max-h-full max-w-full rounded-md border border-border bg-background object-contain dark:border-white/10 dark:bg-white/5"
                            />
                        )}
                    </div>
                )}

                {shouldRenderSource && (
                    <div
                        className="[&>pre]:m-0 [&>pre]:p-4 [&>pre]:text-[13px] [&>pre]:leading-[1.6] [&>pre]:bg-transparent! [&_code]:font-mono [&_code]:text-[13px]"
                        dangerouslySetInnerHTML={{ __html: html }}
                    />
                )}
            </div>
        </div>
    )
}
