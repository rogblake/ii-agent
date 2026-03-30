import {
    FileIcon,
    FileTextIcon,
    FileCodeIcon,
    FileJsonIcon,
    ImageIcon,
    FileTypeIcon,
    FolderIcon,
    FolderOpenIcon,
    TerminalIcon,
    DatabaseIcon,
    SettingsIcon,
    PaletteIcon,
    GlobeIcon,
    LockIcon
} from 'lucide-react'
import { cn } from '@/lib/utils'

const ICON_MAP: Record<string, { icon: typeof FileIcon; color: string }> = {
    // TypeScript / JavaScript
    ts: { icon: FileCodeIcon, color: 'text-blue-400' },
    tsx: { icon: FileCodeIcon, color: 'text-blue-400' },
    js: { icon: FileCodeIcon, color: 'text-yellow-400' },
    jsx: { icon: FileCodeIcon, color: 'text-yellow-400' },
    mjs: { icon: FileCodeIcon, color: 'text-yellow-400' },
    cjs: { icon: FileCodeIcon, color: 'text-yellow-400' },

    // Python
    py: { icon: FileCodeIcon, color: 'text-green-400' },
    pyi: { icon: FileCodeIcon, color: 'text-green-400' },

    // Web
    html: { icon: GlobeIcon, color: 'text-orange-400' },
    css: { icon: PaletteIcon, color: 'text-blue-300' },
    scss: { icon: PaletteIcon, color: 'text-pink-400' },

    // Data
    json: { icon: FileJsonIcon, color: 'text-yellow-300' },
    yaml: { icon: FileTextIcon, color: 'text-red-300' },
    yml: { icon: FileTextIcon, color: 'text-red-300' },
    toml: { icon: FileTextIcon, color: 'text-orange-300' },

    // Docs
    md: { icon: FileTextIcon, color: 'text-sky-blue' },
    mdx: { icon: FileTextIcon, color: 'text-sky-blue' },
    txt: { icon: FileTextIcon, color: 'text-grey-4' },

    // Config
    env: { icon: LockIcon, color: 'text-yellow-500' },
    lock: { icon: LockIcon, color: 'text-grey-4' },
    gitignore: { icon: SettingsIcon, color: 'text-grey-4' },

    // Images
    png: { icon: ImageIcon, color: 'text-green-300' },
    jpg: { icon: ImageIcon, color: 'text-green-300' },
    jpeg: { icon: ImageIcon, color: 'text-green-300' },
    svg: { icon: ImageIcon, color: 'text-orange-300' },
    ico: { icon: ImageIcon, color: 'text-green-300' },
    webp: { icon: ImageIcon, color: 'text-green-300' },
    avif: { icon: ImageIcon, color: 'text-green-300' },
    apng: { icon: ImageIcon, color: 'text-green-300' },
    tif: { icon: ImageIcon, color: 'text-green-300' },
    tiff: { icon: ImageIcon, color: 'text-green-300' },
    heic: { icon: ImageIcon, color: 'text-green-300' },
    heif: { icon: ImageIcon, color: 'text-green-300' },

    // Shell
    sh: { icon: TerminalIcon, color: 'text-green-400' },
    bash: { icon: TerminalIcon, color: 'text-green-400' },

    // Database
    sql: { icon: DatabaseIcon, color: 'text-blue-300' },
    prisma: { icon: DatabaseIcon, color: 'text-teal-300' },

    // Rust / Go / Other
    rs: { icon: FileCodeIcon, color: 'text-orange-400' },
    go: { icon: FileCodeIcon, color: 'text-cyan-400' },
    java: { icon: FileCodeIcon, color: 'text-red-400' },
    rb: { icon: FileCodeIcon, color: 'text-red-400' },
    php: { icon: FileCodeIcon, color: 'text-purple-400' },
    swift: { icon: FileCodeIcon, color: 'text-orange-400' },

    // Other
    dockerfile: { icon: FileTypeIcon, color: 'text-blue-400' },
    graphql: { icon: FileTypeIcon, color: 'text-pink-400' },
    xml: { icon: FileTypeIcon, color: 'text-orange-300' }
}

function getExtension(filename: string): string {
    // Handle dotfiles like .gitignore, .env
    if (filename.startsWith('.')) {
        return filename.slice(1).toLowerCase()
    }
    const parts = filename.split('.')
    if (parts.length <= 1) return ''
    return parts[parts.length - 1].toLowerCase()
}

function getSpecialIcon(
    filename: string
): { icon: typeof FileIcon; color: string } | null {
    const lower = filename.toLowerCase()
    if (lower === 'dockerfile') return ICON_MAP.dockerfile
    if (lower === 'makefile')
        return { icon: TerminalIcon, color: 'text-grey-4' }
    if (lower === 'package.json') return ICON_MAP.json
    if (lower === 'tsconfig.json')
        return { icon: SettingsIcon, color: 'text-blue-400' }
    return null
}

interface FileIconComponentProps {
    name: string
    isDirectory: boolean
    isExpanded?: boolean
    className?: string
}

export function FileIconComponent({
    name,
    isDirectory,
    isExpanded = false,
    className
}: FileIconComponentProps) {
    if (isDirectory) {
        const Icon = isExpanded ? FolderOpenIcon : FolderIcon
        return (
            <Icon
                size={16}
                className={cn(
                    'shrink-0',
                    isExpanded
                        ? 'text-firefly dark:text-sky-blue'
                        : 'text-firefly/70 dark:text-sky-blue/70',
                    className
                )}
            />
        )
    }

    const special = getSpecialIcon(name)
    if (special) {
        const Icon = special.icon
        return (
            <Icon
                size={16}
                className={cn('shrink-0', special.color, className)}
            />
        )
    }

    const ext = getExtension(name)
    const mapping = ICON_MAP[ext]
    if (mapping) {
        const Icon = mapping.icon
        return (
            <Icon
                size={16}
                className={cn('shrink-0', mapping.color, className)}
            />
        )
    }

    return (
        <FileIcon
            size={16}
            className={cn('shrink-0 text-grey-4', className)}
        />
    )
}
