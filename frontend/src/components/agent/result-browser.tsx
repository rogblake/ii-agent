import { useTranslation } from 'react-i18next'

const ResultBrowser = () => {
    const { t } = useTranslation()
    return <div>{t('agent.resultBrowser.placeholder')}</div>
}

export default ResultBrowser
