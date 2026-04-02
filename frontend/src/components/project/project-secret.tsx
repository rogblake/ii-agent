import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Icon } from '@/components/ui/icon'
import { Badge } from '@/components/ui/badge'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'

interface SecretEntry {
    key: string
    value: string
    updatedAt?: string
}

interface ProjectSecretProps {
    secretsEntries: SecretEntry[]
    isLoadingSecrets: boolean
    isSavingSecrets: boolean
    onAddSecret: (secrets: Array<{ key: string; value: string }>) => Promise<void>
    onSecretChange: (
        index: number,
        field: keyof SecretEntry,
        value: string
    ) => void
    onEditSecret: (index: number, key: string, value: string) => Promise<void>
    onRemoveSecret: (index: number) => void
    onSaveSecrets: () => void
    onResetSecrets: () => void
}

// Mock data for missing secrets
const MISSING_SECRETS = [
    'REPLICATE_API_TOKEN',
    'RESEND_API_TOKEN',
    'GOOGLE_AUTHETICATION_TOKEN'
]

interface NewSecretRow {
    key: string
    value: string
}

const ProjectSecret = ({
    secretsEntries,
    isLoadingSecrets,
    isSavingSecrets,
    onAddSecret,
    onEditSecret,
    onRemoveSecret,
}: ProjectSecretProps) => {
    const { t, i18n } = useTranslation()
    const [newSecretRows, setNewSecretRows] = useState<NewSecretRow[]>([
        { key: '', value: '' }
    ])
    const [searchQuery, setSearchQuery] = useState('')
    const [visibleSecrets, setVisibleSecrets] = useState<Set<number>>(new Set())
    const [editingIndex, setEditingIndex] = useState<number | null>(null)
    const [isSearchFocused, setIsSearchFocused] = useState(false)
    const [editSecretKey, setEditSecretKey] = useState('')
    const [editSecretValue, setEditSecretValue] = useState('')
    const [isMissingSecretsAdded, setIsMissingSecretsAdded] = useState(false)

    const isEditing = editingIndex !== null

    const filteredSecrets = useMemo(() => {
        if (!searchQuery.trim()) {
            return secretsEntries.map((entry, index) => ({ entry, index }))
        }
        return secretsEntries
            .map((entry, index) => ({ entry, index }))
            .filter(({ entry }) =>
                entry.key.toLowerCase().includes(searchQuery.toLowerCase())
            )
    }, [secretsEntries, searchQuery])

    const handleAddSecret = async () => {
        const validRows = newSecretRows
            .filter((row) => row.key.trim())
            .map((row) => ({ key: row.key.trim(), value: row.value }))
        if (validRows.length === 0) return
        await onAddSecret(validRows)
        setNewSecretRows([{ key: '', value: '' }])
    }

    const handleSaveEdit = async () => {
        if (editingIndex === null || !editSecretKey.trim()) return
        await onEditSecret(editingIndex, editSecretKey.trim(), editSecretValue)
        setEditingIndex(null)
        setEditSecretKey('')
        setEditSecretValue('')
    }

    const handleCancelEdit = () => {
        setEditingIndex(null)
        setEditSecretKey('')
        setEditSecretValue('')
    }

    const handleRowChange = (
        index: number,
        field: 'key' | 'value',
        value: string
    ) => {
        setNewSecretRows((prev) => {
            const updated = [...prev]
            updated[index] = { ...updated[index], [field]: value }
            return updated
        })
    }

    const handleAddMissingSecrets = () => {
        const missingRows = MISSING_SECRETS.map((secret) => ({
            key: secret,
            value: ''
        }))
        setNewSecretRows(missingRows)
        setIsMissingSecretsAdded(true)
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleAddSecret()
        }
    }

    const toggleSecretVisibility = (index: number) => {
        setVisibleSecrets((prev) => {
            const next = new Set(prev)
            if (next.has(index)) {
                next.delete(index)
            } else {
                next.add(index)
            }
            return next
        })
    }

    const copyToClipboard = async (value: string) => {
        try {
            await navigator.clipboard.writeText(value)
        } catch {
            console.error('Failed to copy to clipboard')
        }
    }

    const formatDate = (dateString?: string) => {
        if (!dateString) {
            return t('project.secrets.time.justNow')
        }
        const date = new Date(dateString)
        return date.toLocaleDateString(i18n.language || undefined, {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        })
    }

    const maskValue = (value: string) => {
        return '•'.repeat(Math.min(value.length, 10))
    }

    const handleStartEdit = (index: number, entry: SecretEntry) => {
        setEditingIndex(index)
        setEditSecretKey(entry.key)
        setEditSecretValue(entry.value)
    }

    const shouldShowMissingSecret = false

    return (
        <div className="space-y-6">
            {/* Add New Secret Section */}
            <div className="rounded-xl bg-firefly/10 dark:bg-sky-blue-2/10 p-4">
                <h3 className="text-base font-semibold text-firefly dark:text-sky-blue-2">
                    {isEditing
                        ? t('project.secrets.form.editTitle')
                        : t('project.secrets.form.addTitle')}
                </h3>
                <p className="mt-1 text-sm text-firefly/70 dark:text-white/70">
                    {isEditing
                        ? t('project.secrets.form.editDescription')
                        : t('project.secrets.form.addDescription')}
                </p>
                {isEditing ? (
                    <>
                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                            <Input
                                placeholder={t(
                                    'project.secrets.form.namePlaceholder'
                                )}
                                value={editSecretKey}
                                onChange={(e) =>
                                    setEditSecretKey(e.target.value)
                                }
                                className="h-12 rounded-xl border-white/20 bg-[#A6FFFF1A] text-white placeholder:text-white/50"
                            />
                            <Input
                                placeholder={t(
                                    'project.secrets.form.valuePlaceholder'
                                )}
                                value={editSecretValue}
                                onChange={(e) =>
                                    setEditSecretValue(e.target.value)
                                }
                                type="password"
                                className="h-12 rounded-xl border-white/20 bg-[#A6FFFF1A] text-white placeholder:text-white/50"
                            />
                        </div>
                        <div className="mt-4 flex gap-2">
                            <Button
                                onClick={handleSaveEdit}
                                disabled={
                                    !editSecretKey.trim() || isSavingSecrets
                                }
                                className="rounded-sm bg-sky-blue text-black"
                            >
                                {isSavingSecrets
                                    ? t('common.saving')
                                    : t('common.save')}
                            </Button>
                            <Button
                                onClick={handleCancelEdit}
                                className="rounded-sm text-red-2"
                            >
                                {t('common.cancel')}
                            </Button>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="mt-4 space-y-3">
                            {newSecretRows.map((row, index) => (
                                <div
                                    key={index}
                                    className="grid gap-4 md:grid-cols-2"
                                >
                                    <Input
                                        placeholder={t(
                                            'project.secrets.form.namePlaceholder'
                                        )}
                                        value={row.key}
                                        onChange={(e) =>
                                            handleRowChange(
                                                index,
                                                'key',
                                                e.target.value
                                            )
                                        }
                                        onKeyDown={handleKeyDown}
                                        className="h-12 rounded-xl border-white/20 bg-firefly/10 dark:bg-[#A6FFFF1A] text-black dark:text-white placeholder:dark:text-white/50"
                                    />
                                    <Input
                                        placeholder={t(
                                            'project.secrets.form.valuePlaceholder'
                                        )}
                                        value={row.value}
                                        onChange={(e) =>
                                            handleRowChange(
                                                index,
                                                'value',
                                                e.target.value
                                            )
                                        }
                                        onKeyDown={handleKeyDown}
                                        type="password"
                                        className="h-12 rounded-xl border-white/20 bg-firefly/10 dark:bg-[#A6FFFF1A] text-black dark:text-white placeholder:dark:text-white/50"
                                    />
                                </div>
                            ))}
                        </div>
                        <div className="mt-4 flex gap-2">
                            <Button
                                onClick={handleAddSecret}
                                disabled={
                                    !newSecretRows.some((row) =>
                                        row.key.trim()
                                    ) || isSavingSecrets
                                }
                                className="rounded-sm bg-sky-blue text-black"
                            >
                                {isSavingSecrets
                                    ? t('common.saving')
                                    : t('project.secrets.actions.addSecret')}
                            </Button>
                        </div>
                    </>
                )}
                {!isMissingSecretsAdded && shouldShowMissingSecret && (
                    <div className="rounded-xl bg-yellow/10 p-4 mt-6">
                        <h3 className="text-base font-semibold text-yellow">
                            {t('project.secrets.missing.title')}
                        </h3>
                        <p className="mt-1 text-sm text-white/70">
                            {t('project.secrets.missing.description')}
                        </p>
                        <ul className="mt-3 list-disc list-inside space-y-1">
                            {MISSING_SECRETS.map((secret) => (
                                <li key={secret} className="text-sm text-white">
                                    {secret}
                                </li>
                            ))}
                        </ul>
                        <Button
                            onClick={handleAddMissingSecrets}
                            className="mt-4 rounded-sm bg-sky-blue text-black"
                        >
                            {t('project.secrets.actions.addSecret')}
                        </Button>
                    </div>
                )}
            </div>

            {/* Secret List Section */}
            <div className="rounded-xl bg-firefly/10 dark:bg-sky-blue-2/10 p-4">
                <h3 className="text-base font-semibold text-firefly dark:text-sky-blue-2">
                    {t('project.secrets.list.title')}
                </h3>
                <div className="mt-4">
                    <div
                        className={`relative transition-opacity ${isSearchFocused || searchQuery ? 'opacity-100' : 'dark:opacity-10'}`}
                    >
                        <Icon
                            name="search"
                            className="absolute left-0 top-3 size-5 -translate-y-1/2 fill-firefly dark:fill-white"
                        />
                        <Input
                            placeholder={t(
                                'project.secrets.list.searchPlaceholder'
                            )}
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onFocus={() => setIsSearchFocused(true)}
                            onBlur={() => setIsSearchFocused(false)}
                            className="h-7 pb-2 rounded-b-none !border-t-transparent !border-x-transparent !border-b border-b-black dark:!border-b-white !bg-transparent dark:!bg-transparent pl-7 text-dark dark:text-white"
                        />
                    </div>
                </div>

                {isLoadingSecrets && (
                    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                        {[...Array(4)].map((_, i) => (
                            <Skeleton
                                key={i}
                                className="h-32 rounded-xl bg-white/10"
                            />
                        ))}
                    </div>
                )}

                {!isLoadingSecrets && filteredSecrets.length === 0 && (
                    <p className="mt-4 text-sm text-black/50 dark:text-white/50">
                        {searchQuery
                            ? t('project.secrets.list.emptySearch')
                            : t('project.secrets.list.empty')}
                    </p>
                )}

                {!isLoadingSecrets && filteredSecrets.length > 0 && (
                    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                        {filteredSecrets.map(({ entry, index }) => (
                            <div
                                key={`secret-${index}`}
                                className={`rounded-xl border bg-firefly dark:bg-[#A6FFFF1A] p-4 ${
                                    editingIndex === index
                                        ? 'border-sky-blue'
                                        : 'border-grey'
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2 flex-1">
                                        <Button
                                            className="!p-0 !h-auto"
                                            onClick={() =>
                                                copyToClipboard(entry.key)
                                            }
                                        >
                                            <Icon
                                                name="copy"
                                                className="size-4 fill-white"
                                            />
                                        </Button>
                                        <span className="text-sm text-white line-clamp-1 break-all">
                                            {entry.key}
                                        </span>
                                        <Badge className="bg-[#A6FFFF1A] text-[10px] text-sky-blue-2">
                                            {t('project.secrets.list.protected')}
                                        </Badge>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <DropdownMenu>
                                            <DropdownMenuTrigger asChild>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="size-5 p-0"
                                                >
                                                    <Icon
                                                        name="more-2"
                                                        className="size-5 stroke-white"
                                                    />
                                                </Button>
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent
                                                align="end"
                                                className="w-42"
                                            >
                                                <DropdownMenuItem
                                                    className="gap-x-[6px]"
                                                    onClick={() =>
                                                        handleStartEdit(
                                                            index,
                                                            entry
                                                        )
                                                    }
                                                >
                                                    <Icon
                                                        name="edit"
                                                        className="mr-2 size-4 fill-black"
                                                    />
                                                    {t(
                                                        'project.secrets.list.menu.edit'
                                                    )}
                                                </DropdownMenuItem>
                                                <DropdownMenuItem
                                                    variant="destructive"
                                                    onClick={() =>
                                                        onRemoveSecret(index)
                                                    }
                                                    className="text-red"
                                                >
                                                    <Icon
                                                        name="trash"
                                                        className="mr-2 size-4"
                                                    />
                                                    {t(
                                                        'project.secrets.list.menu.delete'
                                                    )}
                                                </DropdownMenuItem>
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                    </div>
                                </div>
                                <p className="mt-1 text-xs text-white/50">
                                    {t('project.secrets.list.lastUpdated', {
                                        date: formatDate(entry.updatedAt)
                                    })}
                                </p>
                                <div className="mt-3 flex items-center gap-2 rounded-lg">
                                    <Button
                                        className="!p-0 !h-auto"
                                        onClick={() =>
                                            copyToClipboard(entry.value)
                                        }
                                    >
                                        <Icon
                                            name="copy"
                                            className="size-4 fill-white"
                                        />
                                    </Button>
                                    <div className="flex flex-1 justify-between items-center px-[6px] py-1 bg-white/10 rounded-sm overflow-hidden">
                                        <span className="flex-1 truncate font-mono text-sm text-white/70 min-w-0">
                                            {visibleSecrets.has(index)
                                                ? entry.value
                                                : maskValue(entry.value)}
                                        </span>
                                        <div className="flex items-center gap-1">
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() =>
                                                    toggleSecretVisibility(
                                                        index
                                                    )
                                                }
                                                className="size-3 p-0 !h-auto"
                                            >
                                                <Icon
                                                    name={
                                                        visibleSecrets.has(
                                                            index
                                                        )
                                                            ? 'eye-off'
                                                            : 'eye'
                                                    }
                                                    className="size-3 fill-white"
                                                />
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}

export default ProjectSecret
