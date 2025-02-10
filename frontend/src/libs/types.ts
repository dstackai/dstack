export type FormFieldError = {
    loc: string[];
    msg: string;
    type?: string;
    code: string;
};

export type ResponseServerErrorItem = {
    msg: string;
    code: string;
};

export type ResponseServerError = {
    detail: (FormFieldError | ResponseServerErrorItem)[];
};
