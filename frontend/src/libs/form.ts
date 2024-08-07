import { FormFieldError } from './types';

export const getFieldErrorFromServerResponse = (error: FormFieldError): { fieldNamePath: string; message: string } => {
    const fieldNamePath = error.loc.filter((key) => key !== 'body').join('.');
    const message = error.msg;

    return { fieldNamePath, message };
};
