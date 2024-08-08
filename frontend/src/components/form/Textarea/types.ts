import { ReactNode } from 'react';
import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { TextareaProps } from '@cloudscape-design/components/textarea';

export type FormTextareaProps<T extends FieldValues> = Omit<TextareaProps, 'value' | 'name'> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'> & {
        leftContent?: ReactNode;
    };
