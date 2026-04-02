import clsx from 'clsx'
import { Trans, useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { ProjectDatabaseRecordsResponse } from '@/typings/project'
import { Icon } from '../ui/icon'

const RECORD_PAGE_SIZE = 20

interface ProjectDatabaseProps {
    resolvedProjectId: string | null
    hasDatabaseConfig: boolean
    isLoadingTables: boolean
    tables: string[]
    selectedTable: string
    records: ProjectDatabaseRecordsResponse | null
    isLoadingRecords: boolean
    recordsPageOffset: number
    recordColumns: string[]
    onSelectTable: (table: string) => void
    onRefreshSchema: () => void
    onRefreshRecords: () => void
    onNextPage: () => void
    onPrevPage: () => void
}

function formatCellValue(value: unknown) {
    if (value === null || value === undefined) {
        return ''
    }
    if (typeof value === 'object') {
        try {
            return JSON.stringify(value, null, 2)
        } catch {
            return String(value)
        }
    }
    return String(value)
}

const ProjectDatabase = ({
    resolvedProjectId,
    hasDatabaseConfig,
    isLoadingTables,
    tables,
    selectedTable,
    records,
    isLoadingRecords,
    recordsPageOffset,
    recordColumns,
    onSelectTable,
    onRefreshSchema,
    onRefreshRecords,
    onNextPage,
    onPrevPage
}: ProjectDatabaseProps) => {
    const { t } = useTranslation()
    if (!resolvedProjectId) {
        return (
            <p className="text-sm text-muted-foreground">
                {t('project.database.noProjectInfo')}
            </p>
        )
    }

    if (!hasDatabaseConfig) {
        return (
            <p className="text-sm text-muted-foreground">
                {t('project.database.noDatabaseConfig')}
            </p>
        )
    }

    if (isLoadingTables) {
        return (
            <div className="space-y-3">
                <Skeleton className="h-10 w-40" />
                <Skeleton className="h-64 w-full" />
            </div>
        )
    }

    if (tables.length === 0) {
        return (
            <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                    {t('project.database.noTablesFound')}
                </p>
                <Button variant="outline" size="sm" onClick={onRefreshSchema}>
                    {t('project.database.actions.refreshSchema')}
                </Button>
            </div>
        )
    }

    const pageSize = records?.limit ?? RECORD_PAGE_SIZE
    const pageStart = records ? records.offset + 1 : recordsPageOffset + 1
    const pageEnd = records ? records.offset + records.rows.length : 0
    const hasPrevPage = recordsPageOffset > 0
    const hasNextPage = records
        ? records.offset + records.rows.length < records.total
        : false
    const currentPage = Math.floor(recordsPageOffset / pageSize) + 1

    return (
        <div className="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
            <div className="">
                <ScrollArea className="max-h-[360px]">
                    <div className="flex flex-col gap-1">
                        {tables.map((table) => {
                            const isActive = selectedTable === table
                            return (
                                <button
                                    key={table}
                                    type="button"
                                    onClick={() => onSelectTable(table)}
                                    className={clsx(
                                        'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition',
                                        isActive
                                            ? 'bg-slate-900/5 font-semibold text-slate-900 shadow-sm dark:bg-sky-blue-2/30 dark:text-white'
                                            : 'text-slate-700 hover:bg-white/60 dark:text-white dark:hover:bg-white/5 opacity-30'
                                    )}
                                    aria-pressed={isActive}
                                >
                                    <Icon
                                        name="table"
                                        className="fill-black dark:fill-white size-4"
                                    />
                                    <span className="truncate">{table}</span>
                                </button>
                            )
                        })}
                    </div>
                    <Button
                        size="lg"
                        onClick={onRefreshSchema}
                        disabled={isLoadingTables}
                        className="mt-4 rounded-sm w-full bg-sky-blue text-charcoal px-3 flex justify-center items-center"
                    >
                        <Icon name="refresh" className="stroke-black" />
                        {t('project.database.actions.refresh')}
                    </Button>
                </ScrollArea>
            </div>

            <div className="space-y-3 rounded-2xl border border-white/60 bg-firefly/10 p-4 shadow-inner dark:border-white/10 dark:bg-sky-blue-2/10 min-w-0">
                <div className="flex gap-3 items-center justify-between">
                    <div>
                        <p className="text-base font-semibold text-slate-900 dark:text-sky-blue">
                            {selectedTable ||
                                t('project.database.selectTableToInspect')}
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onRefreshRecords}
                            disabled={!selectedTable || isLoadingRecords}
                            className="border-none"
                        >
                            <Icon
                                name="refresh"
                                className="stroke-black dark:stroke-white"
                            />
                        </Button>
                    </div>
                </div>

                <div className="overflow-hidden rounded-xl border border-black dark:border-white">
                    {isLoadingRecords ? (
                        <div className="p-10 flex justify-center items-center">
                            <Icon
                                name="loading"
                                className="size-6 animate-spin fill-black dark:fill-white"
                            />
                        </div>
                    ) : records && records.rows.length > 0 ? (
                        <ScrollArea className="max-h-[500px] w-full">
                            <div className="min-w-full">
                                <table className="min-w-full table-auto text-sm">
                                    <thead className="sticky top-0 z-10 bg-black/10 dark:bg-white/10">
                                        <tr className="border-b border-black dark:border-white">
                                            <th className="w-16 px-3 py-3 text-left text-xs font-bold text-black dark:text-white border-r border-black dark:border-white">
                                                <div className="flex items-center gap-1">
                                                    {t('project.database.tableHeaders.no')}
                                                </div>
                                            </th>
                                            {recordColumns.map((column) => (
                                                <th
                                                    key={column}
                                                    className={clsx(
                                                        'px-3 py-3 text-left text-xs font-bold text-black dark:text-white border-r border-black dark:border-white',
                                                        {
                                                            'border-none':
                                                                column ===
                                                                recordColumns[
                                                                    recordColumns.length -
                                                                        1
                                                                ]
                                                        }
                                                    )}
                                                >
                                                    <div className="flex items-center gap-1">
                                                        {column}
                                                    </div>
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {records.rows.map((row, rowIndex) => (
                                            <tr
                                                key={`${rowIndex}-${selectedTable}`}
                                                className={
                                                    rowIndex <
                                                    records.rows.length - 1
                                                        ? 'border-b border-black dark:border-white'
                                                        : ''
                                                }
                                            >
                                                <td className="px-3 py-3 text-sm text-black dark:text-white border-r border-black dark:border-white">
                                                    {recordsPageOffset +
                                                        rowIndex +
                                                        1}
                                                </td>
                                                {recordColumns.map((column) => (
                                                    <td
                                                        key={`${rowIndex}-${column}`}
                                                        className={clsx(
                                                            'px-3 py-3 align-top text-sm text-black dark:text-white border-r border-black dark:border-white',
                                                            {
                                                                'border-none':
                                                                    column ===
                                                                    recordColumns[
                                                                        recordColumns.length -
                                                                            1
                                                                    ]
                                                            }
                                                        )}
                                                    >
                                                        <span className="block max-w-[280px] truncate">
                                                            {formatCellValue(
                                                                row[column]
                                                            )}
                                                        </span>
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                            <ScrollBar orientation="horizontal" />
                        </ScrollArea>
                    ) : (
                        <div className="p-4 text-sm text-[#8b97a8]">
                            {selectedTable
                                ? t('project.database.empty.noRows')
                                : t('project.database.empty.selectTable')}
                        </div>
                    )}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl text-xs">
                    <div className="text-slate-500 dark:text-white/60">
                        <Trans
                            i18nKey="project.database.pagination.showingUpTo"
                            values={{ count: records?.total ?? 0 }}
                            components={{
                                count: (
                                    <span className="font-semibold text-firefly dark:text-sky-blue" />
                                )
                            }}
                        />
                    </div>
                    <div className="text-slate-500 dark:text-white/60">
                        <Trans
                            i18nKey="project.database.pagination.range"
                            values={{
                                start: pageStart,
                                end: pageEnd,
                                total: records?.total ?? 0
                            }}
                            components={{
                                range: (
                                    <span className="font-semibold text-firefly dark:text-sky-blue" />
                                ),
                                total: (
                                    <span className="font-semibold text-firefly dark:text-sky-blue" />
                                )
                            }}
                        />
                    </div>
                    <div className="flex items-center gap-3">
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={onPrevPage}
                            disabled={
                                !hasPrevPage ||
                                isLoadingRecords ||
                                !selectedTable
                            }
                            className="border-none"
                        >
                            <Icon
                                name="arrow-square-left"
                                className="size-5 fill-black dark:fill-white"
                            />
                        </Button>
                        <span className="text-slate-500 dark:text-white/60 flex items-center gap-x-1">
                            <span className="text-grey-4">
                                {t('project.database.pagination.page')}
                            </span>
                            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-black dark:border-white font-semibold text-firefly dark:text-white bg-firefly/10 dark:bg-[#A6FFFF1A]">
                                {currentPage}
                            </span>
                            <span className="text-grey-4">
                                {t('project.database.pagination.of')}
                            </span>
                            <span className="font-semibold text-black dark:text-white">
                                {records?.total
                                    ? Math.ceil(records.total / pageSize)
                                        : 1}
                            </span>
                        </span>
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={onNextPage}
                            disabled={
                                !hasNextPage ||
                                isLoadingRecords ||
                                !selectedTable
                            }
                            className="border-none"
                        >
                            <Icon
                                name="arrow-square-right"
                                className="size-5 fill-black dark:fill-white"
                            />
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default ProjectDatabase
