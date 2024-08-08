export type FormValues = {
    amount: number;
};

export interface IProps {
    defaultValues?: Partial<FormValues>;
    isLoading?: boolean;
    onCancel?: () => void;
    onSubmit: (values: FormValues) => void;
}
