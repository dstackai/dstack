import { FieldValues, ControllerProps } from 'react-hook-form';
import { InputProps } from '@cloudscape-design/components/input';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { ReactNode } from 'react';

export type FormInputProps<T extends FieldValues> = Omit<InputProps, 'value' | 'name'> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'> & {
        leftContent?: ReactNode;
    };
