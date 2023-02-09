import { Control, FieldValues, Path } from 'react-hook-form';
import { InputProps } from '@cloudscape-design/components/input';
import { FormFieldProps } from '@cloudscape-design/components/form-field';

export type FormInputProps<T extends FieldValues> = Omit<InputProps, 'value' | 'name'> &
    Omit<FormFieldProps, 'errorText'> & {
        control: Control<T, object>;
        name: Path<T>;
    };
