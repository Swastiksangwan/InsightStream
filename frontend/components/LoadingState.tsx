type LoadingStateProps = {
  message?: string;
};

export function LoadingState({ message = "Loading content..." }: LoadingStateProps) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      {message}
    </div>
  );
}
