import { ReactNode } from 'react';
import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { ToggleProps } from '@cloudscape-design/components/toggle';

export type FormToggleProps<T extends FieldValues> = Omit<ToggleProps, 'value' | 'checked' | 'name'> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules' | 'defaultValue'> & {
        toggleDescription?: ReactNode;
        leftContent?: ReactNode;
        toggleLabel?: ReactNode | string;
        toggleInfo?: ReactNode;
    };
