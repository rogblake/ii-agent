'use client'

import { memo, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeHighlight from 'rehype-highlight'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'

import 'katex/dist/katex.min.css'

interface MarkdownProps {
    children: string | null | undefined
}

// Stable references for plugins - created once at module level
const REMARK_PLUGINS = [remarkGfm, remarkMath]
const REHYPE_PLUGINS = [rehypeRaw, rehypeHighlight, rehypeKatex]

// Stable component overrides - created once at module level
const MARKDOWN_COMPONENTS = {
    a: ({ ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
        <a target="_blank" rel="noopener noreferrer" {...props} />
    )
}

const Markdown = memo(({ children }: MarkdownProps) => {
    // Memoize sanitized content to avoid recalculation
    const sanitizedContent = useMemo(
        () => children?.replace(/(-{20,})/g, '---') || '',
        [children]
    )

    return (
        <div className="markdown-body">
            <ReactMarkdown
                remarkPlugins={REMARK_PLUGINS}
                rehypePlugins={REHYPE_PLUGINS}
                components={MARKDOWN_COMPONENTS}
            >
                {sanitizedContent}
            </ReactMarkdown>
        </div>
    )
})

Markdown.displayName = 'Markdown'

export default Markdown
