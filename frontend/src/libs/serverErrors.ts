import { isArray } from 'lodash';

import { FormFieldError, ResponseServerError } from './types';

export default function serverErrors(error: unknown): error is { data: { message: string } } {
    return (
        typeof error === 'object' &&
        error !== null &&
        'data' in error &&
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        typeof ((error as any).data as any)?.message === 'string'
    );
}

export function isResponseServerFormFieldError(fieldError: unknown): fieldError is FormFieldError {
    return (
        typeof fieldError === 'object' &&
        fieldError !== null &&
        fieldError !== undefined &&
        'loc' in fieldError &&
        'msg' in fieldError &&
        isArray(fieldError?.loc) &&
        typeof fieldError?.msg === 'string'
    );
}

export function isResponseServerError(formErrors: unknown): formErrors is ResponseServerError {
    return (
        typeof formErrors === 'object' &&
        formErrors !== null &&
        formErrors !== undefined &&
        'detail' in formErrors &&
        isArray(formErrors?.detail) &&
        !!formErrors.detail.length &&
        'msg' in formErrors.detail[0]
    );
}

export function getServerError(error: any): string {
    let errorText = error?.error;

    const errorData = error.data;

    if (isResponseServerError(errorData)) {
        const errorDetail = errorData.detail;

        errorText = errorDetail.flatMap(({ msg }) => msg).join(', ');
    }

    return errorText;
}
