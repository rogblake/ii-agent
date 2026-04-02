import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { GlobeIcon, Loader2Icon } from 'lucide-react'
import { toast } from 'sonner'

import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '@/components/ui/select'
import { useForkSessionMutation } from '@/state/api/session.api'
import { useAppSelector, selectAvailableModels } from '@/state'
import type { ForkType } from '@/typings/session'
import type { IModel } from '@/typings/settings'

interface ForkSessionDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    sessionId: string
    attachments: string[]
    forkType: ForkType
}

export function ForkSessionDialog({
    open,
    onOpenChange,
    sessionId,
    attachments,
    forkType
}: ForkSessionDialogProps) {
    const { t } = useTranslation()
    const [additionalInstruction, setAdditionalInstruction] = useState('')
    const [selectedModelId, setSelectedModelId] = useState<string>('')
    const [forkSession, { isLoading }] = useForkSessionMutation()
    const availableModels = useAppSelector(selectAvailableModels)

    const handleFork = async () => {
        try {
            const result = await forkSession({
                sessionId,
                data: {
                    fork_type: forkType,
                    sandbox_mode: 'share',
                    context: {
                        attachments,
                        additional_instruction: additionalInstruction || null
                    },
                    model_setting_id: selectedModelId || null
                }
            }).unwrap()

            // Open the new session in a new tab
            const newSessionUrl = `/${result.session_id}`
            window.open(newSessionUrl, '_blank')

            toast.success(t('fork.success'))
            onOpenChange(false)

            // Reset form
            setAdditionalInstruction('')
            setSelectedModelId('')
        } catch (error) {
            console.error('Failed to fork session:', error)
            toast.error(t('fork.error'))
        }
    }

    const getDialogTitle = () => {
        switch (forkType) {
            case 'research_to_website':
                return t('fork.createWebsite.title')
            case 'research_to_slide':
                return t('fork.createSlide.title')
            default:
                return t('fork.title')
        }
    }

    const getDialogDescription = () => {
        switch (forkType) {
            case 'research_to_website':
                return t('fork.createWebsite.description')
            case 'research_to_slide':
                return t('fork.createSlide.description')
            default:
                return t('fork.description')
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg bg-[rgb(33,33,33)] border border-gray-600 text-white">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-white">
                        <GlobeIcon className="size-5" style={{ color: 'rgb(166, 255, 255)' }} />
                        {getDialogTitle()}
                    </DialogTitle>
                    <DialogDescription className="text-gray-400">
                        {getDialogDescription()}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Model Selection */}
                    <div className="space-y-2">
                        <Label htmlFor="model" className="text-white font-medium">
                            {t('fork.model.label')}
                        </Label>
                        <Select
                            value={selectedModelId}
                            onValueChange={setSelectedModelId}
                        >
                            <SelectTrigger
                                id="model"
                                className="w-full bg-[rgb(45,45,45)] text-white border-gray-600 hover:border-gray-500 focus:border-cyan-300"
                            >
                                <SelectValue
                                    placeholder={t('fork.model.placeholder')}
                                />
                            </SelectTrigger>
                            <SelectContent className="bg-[rgb(45,45,45)] border-gray-600 max-h-[300px]">
                                {availableModels.map((model: IModel) => (
                                    <SelectItem
                                        key={model.id}
                                        value={model.id}
                                        className="text-white hover:bg-[rgb(55,55,55)] focus:bg-[rgb(55,55,55)]"
                                    >
                                        {model.model}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-gray-500">
                            {t('fork.model.hint')}
                        </p>
                    </div>

                    {/* Additional Instructions */}
                    <div className="space-y-2">
                        <Label htmlFor="instructions" className="text-white font-medium">
                            {t('fork.instructions.label')}
                        </Label>
                        <Textarea
                            id="instructions"
                            placeholder={t('fork.instructions.placeholder')}
                            value={additionalInstruction}
                            onChange={(e) =>
                                setAdditionalInstruction(e.target.value)
                            }
                            rows={4}
                            className="resize-none bg-[rgb(45,45,45)] text-white border-gray-600 hover:border-gray-500 focus:border-cyan-300 placeholder:text-gray-500"
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        disabled={isLoading}
                        className="bg-transparent text-white border-gray-600 hover:bg-[rgb(45,45,45)] hover:border-gray-500"
                    >
                        {t('common.cancel')}
                    </Button>
                    <Button
                        onClick={handleFork}
                        disabled={isLoading}
                        className="text-black hover:opacity-80"
                        style={{ backgroundColor: 'rgb(166, 255, 255)' }}
                    >
                        {isLoading ? (
                            <>
                                <Loader2Icon className="size-4 mr-2 animate-spin" />
                                {t('fork.creating')}
                            </>
                        ) : (
                            t('fork.create')
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
