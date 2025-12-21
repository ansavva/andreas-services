/**
 * Extract a user-friendly error message from an error object
 * Handles various error formats from axios, fetch, and custom errors
 */
export function getErrorMessage(
  error: any,
  defaultMessage: string = "An error occurred",
): string {
  // Try to extract error message from various possible formats
  return (
    error?.response?.data?.error || // Backend custom error field
    error?.response?.data?.message || // Backend message field
    error?.response?.data?.detail || // Flask/FastAPI detail field
    error?.message || // JavaScript Error message
    defaultMessage
  );
}

/**
 * Log error to console with context
 */
export function logError(context: string, error: any): void {
  console.error(`[${context}]`, error);

  // Log additional details if available
  if (error?.response) {
    console.error("Response status:", error.response.status);
    console.error("Response data:", error.response.data);
  }
}
