import { cn } from '@/lib/utils'

interface CircularProgressProps {
    value: number // 0-100
    size?: number
    strokeWidth?: number
    className?: string
    showText?: boolean
}

export function CircularProgress({
    value,
    size = 48,
    strokeWidth = 4,
    className,
    showText = true
}: CircularProgressProps) {
    const radius = (size - strokeWidth) / 2
    const circumference = radius * 2 * Math.PI
    const offset = circumference - (value / 100) * circumference

    return (
        <div
            className={cn(
                'relative inline-flex items-center justify-center',
                className
            )}
            style={{ width: size, height: size }}
        >
            <svg
                width={size}
                height={size}
                viewBox={`0 0 ${size} ${size}`}
                className="-rotate-90"
            >
                {/* Background track */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={strokeWidth}
                    className="text-black/10"
                />
                {/* Progress arc */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={strokeWidth}
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                    className="text-firefly dark:text-sky-blue transition-all duration-300"
                />
            </svg>
            {/* Percentage text */}
            {showText && (
                <span className="absolute text-xs font-semibold text-black dark:text-white">
                    {Math.round(value)}%
                </span>
            )}
        </div>
    )
}
