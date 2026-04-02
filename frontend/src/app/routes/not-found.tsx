import { Button } from '@/components/ui/button'
import {
    ErrorView,
    ErrorHeader,
    ErrorDescription,
    ErrorActions
} from '@/features/errors/error-base'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

export default function NotFoundErrorPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    return (
        <ErrorView>
            <ErrorHeader>{t('notFound.title')}</ErrorHeader>
            <ErrorDescription>
                {t('notFound.description')}
            </ErrorDescription>
            <ErrorActions>
                <Button size="lg" onClick={() => navigate(-1)}>
                    {t('common.goBack')}
                </Button>
                <Button size="lg" variant="ghost">
                    {t('notFound.contactSupport')}{' '}
                    <span aria-hidden="true" className="ml-1">
                        &rarr;
                    </span>
                </Button>
            </ErrorActions>
        </ErrorView>
    )
}

// Necessary for react router to lazy load.
export const Component = NotFoundErrorPage
