import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import ButtonIcon from './button-icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuTrigger
} from './ui/dropdown-menu'
import { Icon } from './ui/icon'
import {
    connectorService,
    type GitHubRepository
} from '@/services/connector.service'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

interface ConnectorDropdownProps {
    isDisabled?: boolean
    isGitHubConnected?: boolean
    onGitHubConnect?: () => void
    onRepositorySelect?: (repository: GitHubRepository | undefined) => void
    isOpen?: boolean
    onOpenChange?: (open: boolean) => void
}

const ConnectorDropdown = ({
    isDisabled,
    isGitHubConnected = false,
    onGitHubConnect,
    onRepositorySelect,
    isOpen: controlledIsOpen,
    onOpenChange
}: ConnectorDropdownProps) => {
    const navigate = useNavigate()
    const { t } = useTranslation()
    const [internalIsOpen, setInternalIsOpen] = useState(false)

    // Support both controlled and uncontrolled modes
    const isOpen =
        controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen
    const setIsOpen = (open: boolean) => {
        if (onOpenChange) {
            onOpenChange(open)
        }
        setInternalIsOpen(open)
    }
    const [repositories, setRepositories] = useState<GitHubRepository[]>([])
    const [isLoadingRepos, setIsLoadingRepos] = useState(false)
    const [installationUrl, setInstallationUrl] = useState<string | null>(null)

    // Fetch GitHub app config for installation URL
    useEffect(() => {
        if (isGitHubConnected) {
            connectorService
                .getGitHubAppConfig()
                .then((appConfig) => {
                    setInstallationUrl(appConfig.installation_url)
                })
                .catch((error) => {
                    console.error('Failed to load GitHub app config', error)
                })
        }
    }, [isGitHubConnected])

    useEffect(() => {
        if (isGitHubConnected && isOpen) {
            loadRepositories()
        }
    }, [isGitHubConnected, isOpen])

    const loadRepositories = async () => {
        try {
            setIsLoadingRepos(true)
            const response = await connectorService.getGitHubRepositories()
            setRepositories(response.repositories)
        } catch (error: unknown) {
            console.error('Failed to load GitHub repositories:', error)
            // Show the specific error message from the backend if available
            const axiosError = error as {
                response?: { data?: { detail?: string } }
            }
            const errorMessage =
                axiosError.response?.data?.detail ||
                t('connectors.github.loadRepoError')
            toast.error(errorMessage)
        } finally {
            setIsLoadingRepos(false)
        }
    }

    const handleGitHubClick = () => {
        if (!isGitHubConnected && onGitHubConnect) {
            setIsOpen(false)
            onGitHubConnect()
        }
    }

    const handleRepositoryClick = (repository: GitHubRepository) => {
        setIsOpen(false)
        onRepositorySelect?.(repository)
    }

    const handleConfigureClick = () => {
        setIsOpen(false)
        navigate('/settings/account')
    }

    return (
        <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
            <DropdownMenuTrigger asChild>
                <ButtonIcon name="connector" disabled={isDisabled} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64">
                {isGitHubConnected ? (
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="cursor-pointer">
                            <Icon
                                name="github"
                                className="size-5 fill-black mr-2"
                            />
                            {t('connectors.github.title')}
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent className="w-64 p-0 flex flex-col">
                            <div className="max-h-[250px] overflow-y-auto p-1">
                                {isLoadingRepos ? (
                                    <DropdownMenuItem disabled>
                                        <Icon
                                            name="loading"
                                            className="size-5 animate-spin fill-black"
                                        />
                                        {t('connectors.github.loadingRepos')}
                                    </DropdownMenuItem>
                                ) : repositories.length === 0 ? (
                                    <DropdownMenuItem disabled>
                                        {t('connectors.github.noRepositories')}
                                    </DropdownMenuItem>
                                ) : (
                                    repositories.map((repo) => (
                                        <DropdownMenuItem
                                            key={repo.id}
                                            onClick={() =>
                                                handleRepositoryClick(repo)
                                            }
                                            className="cursor-pointer flex-col items-start"
                                        >
                                            <div className="flex items-center gap-2 w-full">
                                                <span className="truncate font-medium">
                                                    {repo.name}
                                                </span>
                                            </div>
                                            {repo.description && (
                                                <span className="text-xs text-black/60 truncate w-full">
                                                    {repo.description}
                                                </span>
                                            )}
                                        </DropdownMenuItem>
                                    ))
                                )}
                            </div>
                            {installationUrl && (
                                <div className="border-t border-grey-2 p-1">
                                    <DropdownMenuItem
                                        onClick={() => {
                                            window.open(
                                                installationUrl,
                                                '_blank',
                                                'noopener,noreferrer'
                                            )
                                        }}
                                        className="cursor-pointer"
                                    >
                                        <Icon
                                            name="setting-2"
                                            className="size-5 fill-black"
                                        />
                                        {t('connectors.github.configureRepos')}
                                    </DropdownMenuItem>
                                </div>
                            )}
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                ) : (
                    <DropdownMenuItem
                    onClick={handleGitHubClick}
                    disabled={isDisabled || !onGitHubConnect}
                    className="cursor-pointer"
                >
                    <Icon name="github" className="size-5 fill-black" />
                    {t('connectors.github.connect')}
                </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                    onClick={handleConfigureClick}
                    className="cursor-pointer"
                >
                    <Icon name="setting-2" className="size-5 fill-black" />
                    {t('connectors.configure')}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

export default ConnectorDropdown
