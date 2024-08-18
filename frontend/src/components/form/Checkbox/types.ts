import { ReactNode } from 'react';
import { ControllerProps, FieldValues } from 'react-hook-form';
import { CheckboxProps } from '@cloudscape-design/components/checkbox';
import { FormFieldProps } from '@cloudscape-design/components/form-field';

export type FormCheckboxProps<T extends FieldValues> = Omit<CheckboxProps, 'value' | 'checked' | 'name'> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'> & {
        leftContent?: ReactNode;
        checkboxLabel?: string;
    };
