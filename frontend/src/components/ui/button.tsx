import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
    "inline-flex items-center cursor-pointer justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
    {
        variants: {
            variant: {
                default:
                    'bg-primary text-primary-foreground hover:bg-primary/90',
                destructive:
                    'bg-red-2 text-white hover:bg-red-2/90 focus-visible:ring-red-2/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60 dark:hover:bg-destructive/90',
                outline:
                    'border border-charcoal bg-transparent dark:bg-transparent dark:border-input',
                secondary:
                    'bg-secondary text-secondary-foreground hover:bg-secondary/80',
                ghost: '',
                link: 'text-primary underline-offset-4 hover:underline'
            },
            size: {
                default: 'h-9 px-4 py-2 has-[>svg]:px-3 text-sm',
                sm: 'h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 text-sm',
                lg: 'h-10 rounded-md px-6 has-[>svg]:px-4 text-sm',
                xl: 'h-12 rounded-xl px-6 has-[>svg]:px-4 text-md',
                icon: 'size-9'
            }
        },
        defaultVariants: {
            variant: 'default',
            size: 'default'
        }
    }
)

function Button({
    className,
    variant,
    size,
    asChild = false,
    ...props
}: React.ComponentProps<'button'> &
    VariantProps<typeof buttonVariants> & {
        asChild?: boolean
    }) {
    const Comp = asChild ? Slot : 'button'

    return (
        <Comp
            data-slot="button"
            className={cn(buttonVariants({ variant, size, className }))}
            {...props}
        />
    )
}

export { Button, buttonVariants }
