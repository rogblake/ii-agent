import type { ImgHTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { Icon } from './ui/icon'

type LogoProps = {
    className?: string
    imageClassName?: string
    label?: ReactNode
    labelClassName?: string
    labelWrapperClassName?: string
    showBeta?: boolean
    betaLabel?: ReactNode
    betaClassName?: string
    alt?: string
    showIconWhenCollapsed?: boolean
} & Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'alt' | 'className'>

export function Logo({
    className,
    imageClassName,
    label,
    labelClassName,
    labelWrapperClassName,
    showBeta = false,
    betaLabel = 'BETA',
    betaClassName,
    alt = 'Logo',
    showIconWhenCollapsed = false,
    ...imgProps
}: LogoProps) {
    const isSage = useIsSageTheme()

    if (isSage)
        return (
            <div
                className={cn('relative flex items-center gap-x-2', className)}
            >
                {showIconWhenCollapsed && (
                    <img
                        src="/images/sage-icon.png"
                        alt={alt}
                        className={`h-6 md:h-10 hidden group-data-[collapsible=icon]:inline`}
                    />
                )}
                <img
                    src="/images/logo-sage.png"
                    alt={alt}
                    className={`h-6 md:h-10 ${showIconWhenCollapsed && 'group-data-[collapsible=icon]:hidden'} ${imageClassName}`}
                />
            </div>
        )

    return (
        <div className={cn('relative flex items-center gap-x-2', className)}>
            <Icon
                name="logo"
                className={`text-charcoal dark:text-sky-blue ${imageClassName}`}
                {...imgProps}
            />
            {showBeta || labelWrapperClassName ? (
                <div className={labelWrapperClassName}>
                    {label ? (
                        <span className={cn(labelClassName)}>{label}</span>
                    ) : null}
                    {showBeta ? (
                        <span
                            className={cn(
                                'text-[10px] absolute -right-8 -top-1',
                                betaClassName
                            )}
                        >
                            {betaLabel}
                        </span>
                    ) : null}
                </div>
            ) : label ? (
                <span className={cn(labelClassName)}>{label}</span>
            ) : null}
        </div>
    )
}
