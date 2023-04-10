import { isArray } from 'lodash';
import { FormFieldError, FormErrors, RequestErrorWithDetail, FormErrors2 } from './types';

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

export function isRequestErrorWithDetail(requestError: unknown): requestError is RequestErrorWithDetail {
    return (
        typeof requestError === 'object' &&
        requestError !== null &&
        requestError !== undefined &&
        'detail' in requestError &&
        typeof requestError?.detail === 'string'
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

export function isRequestFormErrors2(formErrors: unknown): formErrors is FormErrors2 {
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
