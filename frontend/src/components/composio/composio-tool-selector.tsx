import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Icon } from '@/components/ui/icon'
import { Button } from '@/components/ui/button'
import type { ComposioAction } from '@/state/api/composio.api'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from '@/components/ui/collapsible'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'

interface ComposioToolSelectorProps {
    actions: ComposioAction[]
    categories: string[]
    selectedTools: Set<string>
    onSelectionChange: (selected: Set<string>) => void
}

export function ComposioToolSelector({
    actions,
    categories,
    selectedTools,
    onSelectionChange
}: ComposioToolSelectorProps) {
    const { t } = useTranslation()
    const [searchQuery, setSearchQuery] = useState('')
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
        new Set(categories)
    )

    // Group actions by category
    const toolsByCategory = useMemo(() => {
        const grouped = new Map<string, ComposioAction[]>()

        actions.forEach((action) => {
            const category = action.category || 'Other'
            if (!grouped.has(category)) {
                grouped.set(category, [])
            }
            grouped.get(category)!.push(action)
        })

        return Array.from(grouped.entries()).map(([name, tools]) => ({
            name,
            tools
        }))
    }, [actions])

    // Filter by search
    const filteredCategories = useMemo(() => {
        if (!searchQuery) return toolsByCategory

        const query = searchQuery.toLowerCase()
        return toolsByCategory
            .map((category) => ({
                ...category,
                tools: category.tools.filter(
                    (tool) =>
                        tool.name.toLowerCase().includes(query) ||
                        tool.description.toLowerCase().includes(query)
                )
            }))
            .filter((category) => category.tools.length > 0)
    }, [toolsByCategory, searchQuery])

    const handleCategoryToggle = (categoryName: string) => {
        const newExpanded = new Set(expandedCategories)
        if (newExpanded.has(categoryName)) {
            newExpanded.delete(categoryName)
        } else {
            newExpanded.add(categoryName)
        }
        setExpandedCategories(newExpanded)
    }

    const handleCategorySelectAll = (
        categoryName: string,
        checked: boolean
    ) => {
        const category = toolsByCategory.find((c) => c.name === categoryName)
        if (!category) return

        const newSelection = new Set(selectedTools)
        category.tools.forEach((tool) => {
            if (checked) {
                // Limit to max 20 tools
                if (newSelection.size < 20) {
                    newSelection.add(tool.name)
                }
            } else {
                newSelection.delete(tool.name)
            }
        })
        onSelectionChange(newSelection)
    }

    const handleToolToggle = (toolName: string, checked: boolean) => {
        const newSelection = new Set(selectedTools)
        if (checked) {
            // Limit to max 20 tools
            if (newSelection.size >= 20) {
                return
            }
            newSelection.add(toolName)
        } else {
            newSelection.delete(toolName)
        }
        onSelectionChange(newSelection)
    }

    const handleSelectDefault = () => {
        const DefaultTools = new Set(
            actions
                .filter((a) => a.default_enabled)
                .slice(0, 20)
                .map((a) => a.name)
        )
        onSelectionChange(DefaultTools)
    }

    // Count default (Default) tools that are selected
    const defaultToolsSelectedCount = useMemo(() => {
        return Array.from(selectedTools).filter((toolName) => {
            const action = actions.find((a) => a.name === toolName)
            return action?.default_enabled
        }).length
    }, [selectedTools, actions])

    // Get total number of tools and max selectable
    const totalTools = actions.length
    const maxSelectableTools = Math.min(totalTools, 20)

    const handleSelectNone = () => {
        onSelectionChange(new Set())
    }

    const isCategorySelected = (categoryName: string) => {
        const category = toolsByCategory.find((c) => c.name === categoryName)
        if (!category) return false

        const selectedCount = category.tools.filter((t) =>
            selectedTools.has(t.name)
        ).length
        return selectedCount === category.tools.length
    }

    const getCategorySelectedCount = (categoryName: string) => {
        const category = toolsByCategory.find((c) => c.name === categoryName)
        if (!category) return 0
        return category.tools.filter((t) => selectedTools.has(t.name)).length
    }

    return (
        <div className="space-y-4">
            {/* Quick Actions */}
            <div className="flex items-center justify-between gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-700">
                        {t('composio.toolSelector.defaultToolsSelected', {
                            count: defaultToolsSelectedCount,
                            selected: selectedTools.size,
                            max: maxSelectableTools
                        })}
                    </span>
                </div>
                <div className="flex gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleSelectDefault}
                        className="h-8 px-3 text-xs text-black border-gray-200 hover:bg-gray-100"
                    >
                        {t('composio.toolSelector.default')}
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleSelectNone}
                        className="h-8 px-3 text-xs text-black border-gray-200 hover:bg-gray-100"
                    >
                        {t('composio.toolSelector.clear')}
                    </Button>
                </div>
            </div>

            {/* Search */}
            <div className="relative">
                <Icon
                    name="search"
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 fill-gray-400"
                />
                <Input
                    placeholder={t('composio.toolSelector.searchPlaceholder')}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10 h-11 !text-black placeholder:text-black/50 !bg-black/10"
                />
            </div>

            {/* Categories */}
            <div className="space-y-2">
                {filteredCategories.map((category) => {
                    const isExpanded = expandedCategories.has(category.name)
                    const selectedCount = getCategorySelectedCount(
                        category.name
                    )
                    const isAllSelected = isCategorySelected(category.name)

                    return (
                        <Collapsible
                            key={category.name}
                            open={isExpanded}
                            onOpenChange={() =>
                                handleCategoryToggle(category.name)
                            }
                        >
                            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden hover:shadow-sm transition-shadow">
                                {/* Category Header */}
                                <CollapsibleTrigger className="w-full px-4 py-3.5 flex items-center justify-between bg-sky-blue hover:bg-sky-200/80 transition-colors group">
                                    <div className="flex items-center gap-3 flex-1 min-w-0">
                                        <Checkbox
                                            checked={isAllSelected}
                                            onCheckedChange={(checked) =>
                                                handleCategorySelectAll(
                                                    category.name,
                                                    !!checked
                                                )
                                            }
                                            onClick={(e) => e.stopPropagation()}
                                            className="border-black data-[state=checked]:bg-charcoal data-[state=checked]:border-charcoal"
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <span className="font-medium text-gray-900 text-sm">
                                                    {category.name}
                                                </span>
                                                <Badge
                                                    variant="secondary"
                                                    className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 font-medium"
                                                >
                                                    {selectedCount}/
                                                    {category.tools.length}
                                                </Badge>
                                            </div>
                                        </div>
                                        <Icon
                                            name="chevron-down"
                                            className={`w-4 h-4 text-gray-400 transition-transform duration-200 group-hover:text-gray-600 ${
                                                isExpanded ? 'rotate-180' : ''
                                            }`}
                                        />
                                    </div>
                                </CollapsibleTrigger>

                                {/* Category Content */}
                                <CollapsibleContent>
                                    <div className="border-t border-gray-100">
                                        {category.tools.map((tool, index) => (
                                            <div
                                                key={tool.name}
                                                className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50/50 transition-colors ${
                                                    index !==
                                                    category.tools.length - 1
                                                        ? 'border-b border-gray-50'
                                                        : ''
                                                }`}
                                            >
                                                <Checkbox
                                                    checked={selectedTools.has(
                                                        tool.name
                                                    )}
                                                    onCheckedChange={(
                                                        checked
                                                    ) =>
                                                        handleToolToggle(
                                                            tool.name,
                                                            !!checked
                                                        )
                                                    }
                                                    className="mt-0.5 border-black data-[state=checked]:bg-charcoal data-[state=checked]:border-charcoal"
                                                />
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className="text-sm font-medium text-gray-900">
                                                            {tool.name
                                                                .replace(
                                                                    /_/g,
                                                                    ' '
                                                                )
                                                                .toLowerCase()
                                                                .replace(
                                                                    /\b\w/g,
                                                                    (l) =>
                                                                        l.toUpperCase()
                                                                )}
                                                        </span>
                                                        {tool.default_enabled && (
                                                            <Badge className="bg-emerald-50 text-green border-green text-xs px-2 py-0 font-medium">
                                                                {t(
                                                                    'composio.toolSelector.badges.default'
                                                                )}
                                                            </Badge>
                                                        )}
                                                        {tool.read_only && (
                                                            <Badge className="bg-sky-50 text-violet border-violet text-xs px-2 py-0 font-medium">
                                                                {t(
                                                                    'composio.toolSelector.badges.readOnly'
                                                                )}
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-gray-500 leading-relaxed">
                                                        {tool.description}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CollapsibleContent>
                            </div>
                        </Collapsible>
                    )
                })}

                {filteredCategories.length === 0 && (
                    <div className="text-center py-12">
                        <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                            <Icon
                                name="search"
                                className="w-5 h-5 text-gray-400"
                            />
                        </div>
                        <p className="text-sm font-medium text-gray-900 mb-1">
                            {t('composio.toolSelector.noToolsFound')}
                        </p>
                        <p className="text-xs text-gray-500">
                            {t('composio.toolSelector.noToolsFoundDescription')}
                        </p>
                    </div>
                )}
            </div>
        </div>
    )
}
