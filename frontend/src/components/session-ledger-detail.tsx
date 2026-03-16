import { useMemo, useState } from 'react'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { useNavigate, useParams } from 'react-router'

dayjs.extend(utc)

import { cn } from '@/lib/utils'
import { useGetSessionLedgerQuery } from '@/state'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from './ui/table'
import { Icon } from './ui/icon'

const formatDecimal = (value: number) =>
    value.toLocaleString('en-US', {
        minimumFractionDigits: 6,
        maximumFractionDigits: 6
    })

const SessionLedgerDetail = () => {
    const navigate = useNavigate()
    const { sessionId } = useParams<{ sessionId: string }>()
    const [page, setPage] = useState(1)
    const perPage = 50

    const { data, isLoading } = useGetSessionLedgerQuery(
        { sessionId: sessionId!, page, perPage },
        { skip: !sessionId }
    )

    const totalPages = useMemo(() => {
        if (!data?.total) return 1
        return Math.max(1, Math.ceil(data.total / perPage))
    }, [data?.total])

    const handleBack = () => {
        navigate(-1)
    }

    return (
        <div className="p-3 md:p-0 min-h-screen bg-background">
            <div className="max-w-5xl mx-auto md:pb-8 md:pt-16">
                <div className="flex items-center gap-x-3 md:gap-x-4 mb-6">
                    <button className="cursor-pointer" onClick={handleBack}>
                        <Icon
                            name="arrow-left"
                            className="size-8 hidden dark:inline"
                        />
                        <Icon
                            name="arrow-left-dark"
                            className="size-8 inline dark:hidden"
                        />
                    </button>
                    <div className="flex flex-col">
                        <span className="text-black dark:text-sky-blue text-2xl md:text-[32px] font-semibold">
                            Session Ledger
                        </span>
                        <span className="text-xs text-black/40 dark:text-white/40 font-mono mt-1">
                            {sessionId}
                        </span>
                    </div>
                </div>

                <div className="rounded-2xl overflow-x-auto">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="py-3 text-xs w-[60px]">
                                    ID
                                </TableHead>
                                <TableHead className="py-3 text-xs w-[120px]">
                                    Type
                                </TableHead>
                                <TableHead className="py-3 text-xs w-[100px]">
                                    Domain
                                </TableHead>
                                <TableHead className="py-3 text-xs text-right w-[120px]">
                                    Delta Credits
                                </TableHead>
                                <TableHead className="py-3 text-xs text-right w-[120px]">
                                    Delta Bonus
                                </TableHead>
                                <TableHead className="py-3 text-xs text-right w-[120px]">
                                    Balance After
                                </TableHead>
                                <TableHead className="py-3 text-xs w-[140px]">
                                    Idempotency Key
                                </TableHead>
                                <TableHead className="py-3 text-xs w-[130px]">
                                    Created At
                                </TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {isLoading && (
                                <TableRow>
                                    <TableCell
                                        className="py-6 pl-4"
                                        colSpan={8}
                                    >
                                        Loading...
                                    </TableCell>
                                </TableRow>
                            )}
                            {!isLoading &&
                                data?.entries?.length === 0 && (
                                    <TableRow>
                                        <TableCell
                                            className="py-6 pl-4"
                                            colSpan={8}
                                        >
                                            No ledger entries for this session.
                                        </TableCell>
                                    </TableRow>
                                )}
                            {!isLoading &&
                                data?.entries?.map((entry) => (
                                    <TableRow
                                        key={entry.id}
                                        className="border-0"
                                    >
                                        <TableCell className="py-2 text-xs font-mono tabular-nums">
                                            {entry.id}
                                        </TableCell>
                                        <TableCell className="py-2 text-xs">
                                            <span
                                                className={cn(
                                                    'inline-block px-1.5 py-0.5 rounded text-[10px] font-medium',
                                                    entry.entry_type ===
                                                        'deduction'
                                                        ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                                        : entry.entry_type ===
                                                            'grant' ||
                                                            entry.entry_type ===
                                                                'bonus_grant'
                                                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                                          : entry.entry_type ===
                                                              'reservation_hold'
                                                            ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                                                            : entry.entry_type ===
                                                                'reservation_release'
                                                              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                                                              : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
                                                )}
                                            >
                                                {entry.entry_type}
                                            </span>
                                        </TableCell>
                                        <TableCell className="py-2 text-xs text-black/60 dark:text-white/60">
                                            {entry.source_domain || '-'}
                                        </TableCell>
                                        <TableCell
                                            className={cn(
                                                'py-2 text-xs text-right font-mono tabular-nums',
                                                entry.delta_credits < 0
                                                    ? 'text-red-600 dark:text-red-400'
                                                    : entry.delta_credits > 0
                                                      ? 'text-green-600 dark:text-green-400'
                                                      : ''
                                            )}
                                        >
                                            {entry.delta_credits > 0
                                                ? '+'
                                                : ''}
                                            {formatDecimal(
                                                entry.delta_credits
                                            )}
                                        </TableCell>
                                        <TableCell
                                            className={cn(
                                                'py-2 text-xs text-right font-mono tabular-nums',
                                                entry.delta_bonus_credits < 0
                                                    ? 'text-red-600 dark:text-red-400'
                                                    : entry.delta_bonus_credits >
                                                        0
                                                      ? 'text-green-600 dark:text-green-400'
                                                      : 'text-black/30 dark:text-white/30'
                                            )}
                                        >
                                            {formatDecimal(
                                                entry.delta_bonus_credits
                                            )}
                                        </TableCell>
                                        <TableCell className="py-2 text-xs text-right font-mono tabular-nums">
                                            {entry.balance_after_credits != null
                                                ? formatDecimal(
                                                      entry.balance_after_credits
                                                  )
                                                : '-'}
                                        </TableCell>
                                        <TableCell className="py-2 text-[10px] font-mono text-black/40 dark:text-white/40 max-w-[140px] truncate">
                                            {entry.idempotency_key || '-'}
                                        </TableCell>
                                        <TableCell className="py-2 text-xs">
                                            {dayjs
                                                .utc(entry.created_at)
                                                .local()
                                                .format(
                                                    'DD MMM HH:mm:ss.SSS'
                                                )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                        </TableBody>
                    </Table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2 py-4 select-none">
                        <button
                            type="button"
                            onClick={() =>
                                setPage((p) => Math.max(1, p - 1))
                            }
                            disabled={page === 1}
                            className={cn(
                                'px-2 py-1 text-sm text-black dark:text-white cursor-pointer',
                                page === 1 && 'opacity-50 cursor-not-allowed'
                            )}
                        >
                            Prev
                        </button>
                        <span className="px-2 py-1 text-sm">
                            {page} / {totalPages}
                        </span>
                        <button
                            type="button"
                            onClick={() =>
                                setPage((p) =>
                                    Math.min(totalPages, p + 1)
                                )
                            }
                            disabled={page === totalPages}
                            className={cn(
                                'px-2 py-1 text-sm text-black dark:text-white cursor-pointer',
                                page === totalPages &&
                                    'opacity-50 cursor-not-allowed'
                            )}
                        >
                            Next
                        </button>
                    </div>
                )}
            </div>
        </div>
    )
}

export default SessionLedgerDetail
