import { Button } from './ui/button'
import { Icon } from './ui/icon'

interface SubmitButtonProps {
  isLoading: boolean
  isCreatingSession: boolean
  isCancelling: boolean
  disabled: boolean
  onCancel?: () => void
  onSubmit: () => void
}

const SubmitButton = ({ isLoading, isCreatingSession, isCancelling, disabled, onCancel, onSubmit }: SubmitButtonProps) => {
  // Show spinner while cancellation is in progress
  if (isCancelling) {
    return (
      <Button disabled className="cursor-not-allowed size-7 p-0 !bg-white rounded-full shadow-[0_4px_10px_rgba(0,0,0,0.2)]">
        <Icon name="loading" className="animate-spin size-4 fill-black" />
      </Button>
    )
  }

  if (isLoading && onCancel) {
    return (
      <Button onClick={onCancel} className="cursor-pointer size-7 p-0 !bg-white rounded-full hover:scale-105 active:scale-95 transition-transform shadow-[0_4px_10px_rgba(0,0,0,0.2)]">
        <div className="size-4 rounded-xs bg-black" />
      </Button>
    )
  }

  return (
    <Button
      disabled={disabled}
      onClick={onSubmit}
      className={`cursor-pointer size-7 font-semibold ${isCreatingSession ? '' : 'bg-firefly dark:bg-sky-blue'} rounded-full`}
    >
      {isCreatingSession ? (
        <Icon name="loading" className="animate-spin size-7 fill-black dark:fill-white" />
      ) : (
        <Icon name="arrow-up" className="fill-white dark:fill-black" />
      )}
    </Button>
  )
}

export default SubmitButton

