import { isArray } from 'lodash';
import { FormFieldError, FormErrors } from './types';

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

export function isRequestFormFieldError(fieldError: unknown): fieldError is FormFieldError {
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

export function isRequestFormErrors(formErrors: unknown): formErrors is FormErrors {
    return (
        typeof formErrors === 'object' &&
        formErrors !== null &&
        formErrors !== undefined &&
        'detail' in formErrors &&
        isArray(formErrors?.detail) &&
        isRequestFormFieldError(formErrors.detail[0])
    );
}
