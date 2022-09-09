export default function isErrorWithMessage(error: unknown): error is { data: { message: string } } {
    return (
        typeof error === 'object' &&
        error !== null &&
        'data' in error &&
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        typeof ((error as any).data as any)?.message === 'string'
    );
}

export function isErrorWithError(error: unknown): error is { data: { error: string } } {
    return (
        typeof error === 'object' &&
        error !== null &&
        'data' in error &&
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        typeof ((error as any).data as any)?.error === 'string'
    );
}
