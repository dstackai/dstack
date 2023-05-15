export type FormFieldError = {
    loc: string[];
    msg: string;
    type?: string;
    code: string;
};

export type FormError = {
    msg: string;
    code: string;
};

export type FormErrors = {
    detail: FormFieldError[];
};

export type FormErrors2 = {
    detail: (FormFieldError | FormError)[];
};

export type RequestErrorWithDetail = {
    detail: string;
};
