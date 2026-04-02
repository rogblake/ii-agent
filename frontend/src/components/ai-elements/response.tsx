'use client'

import { cn } from '@/lib/utils'
import { type ComponentProps, memo } from 'react'
import { Streamdown, defaultRehypePlugins } from 'streamdown'
import { CustomCode } from './custom-code'
import { ClickableImage } from '../ui/fullscreen-image-modal'

type ResponseProps = ComponentProps<typeof Streamdown>

const CustomImage = ({ src, alt, ...props }: ComponentProps<'img'>) => (
    <ClickableImage
        {...props}
        src={src || ''}
        alt={alt || ''}
        className="max-w-full md:max-w-1/3 h-auto rounded-md"
    />
)

export const Response = memo(
    ({ className, ...props }: ResponseProps) => (
        <Streamdown
            className={cn(
                'size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 text-black dark:text-white',
                className
            )}
            rehypePlugins={[
                defaultRehypePlugins.raw,
                defaultRehypePlugins.katex
            ]}
            components={{
                code: CustomCode,
                img: CustomImage
            }}
            {...props}
        />
    ),
    (prevProps, nextProps) => prevProps.children === nextProps.children
)

Response.displayName = 'Response'
