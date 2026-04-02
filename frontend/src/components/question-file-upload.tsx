import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import ButtonIcon from './button-icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from './ui/dropdown-menu'
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger
} from '@/components/ui/tooltip'
import { Icon } from './ui/icon'
import ComposioIntegrationsModal from './composio/composio-integrations-modal'

interface QuestionFileUploadProps {
    onFileChange: (files: File[]) => void
    onGoogleDriveClick?: () => void
    isDisabled?: boolean
    isGoogleDriveConnected?: boolean
    isGoogleDriveAuthLoading?: boolean
}

const QuestionFileUpload = ({
    onFileChange,
    isDisabled
}: QuestionFileUploadProps) => {
    const { t } = useTranslation()
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [isOpen, setIsOpen] = useState(false)
    const [isComposioModalOpen, setIsComposioModalOpen] = useState(false)

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files) return

        const filesToUpload = Array.from(e.target.files)
        onFileChange(filesToUpload)

        e.target.value = ''
    }

    const handleLocalUpload = () => {
        fileInputRef.current?.click()
        setIsOpen(false)
    }

    const handleConnectApps = () => {
        setIsOpen(false)
        setIsComposioModalOpen(true)
    }

    return (
        <>
            <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <DropdownMenuTrigger asChild>
                            <ButtonIcon
                                name="plus"
                                disabled={isDisabled}
                                aria-label={t('tooltips.addAttachments')}
                            />
                        </DropdownMenuTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                        {t('tooltips.addAttachments')}
                    </TooltipContent>
                </Tooltip>
                <DropdownMenuContent align="start" className="w-64">
                    <DropdownMenuItem
                        onClick={handleLocalUpload}
                        disabled={isDisabled}
                        className="cursor-pointer"
                    >
                        <Icon name="link" className="size-5 fill-black" />
                        {t('questionFileUpload.addImagesAndFiles')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                        onClick={handleConnectApps}
                        disabled={isDisabled}
                        className="cursor-pointer"
                    >
                        <Icon name="connector" className="size-5 fill-black" />
                        {t('questionFileUpload.connectApps')}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>

            <ComposioIntegrationsModal
                open={isComposioModalOpen}
                onOpenChange={setIsComposioModalOpen}
            />

            <input
                ref={fileInputRef}
                id="file-upload"
                type="file"
                multiple
                className="hidden"
                onChange={handleFileChange}
                disabled={isDisabled}
            />
        </>
    )
}

export default QuestionFileUpload
