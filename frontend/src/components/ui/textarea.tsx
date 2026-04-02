import * as React from 'react'

import { cn } from '@/lib/utils'

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
    return (
        <textarea
            data-slot="textarea"
            className={cn(
                'border-charcoal dark:border-white placeholder:text-black/30 dark:placeholder:text-white/30 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive bg-[#f8fafb] dark:bg-[#A6FFFF1A] text-black dark:text-white flex field-sizing-content min-h-16 w-full rounded-xl border px-4 py-3 shadow-xs transition-[color,box-shadow] outline-none disabled:cursor-not-allowed disabled:opacity-50 text-sm',
                className
            )}
            {...props}
        />
    )
}

export { Textarea }
