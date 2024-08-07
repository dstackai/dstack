import { ReactNode } from 'react';
import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { InputProps } from '@cloudscape-design/components/input';

export type FormInputProps<T extends FieldValues> = Omit<InputProps, 'value' | 'name'> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'> & {
        leftContent?: ReactNode;
        hotspotId?: string;
    };
