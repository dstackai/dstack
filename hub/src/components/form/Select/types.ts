import { Control, FieldValues, Path } from 'react-hook-form';
import { SelectProps } from '@cloudscape-design/components/select';
import { FormFieldProps } from '@cloudscape-design/components/form-field';

export type FormSelectProps<T extends FieldValues> = Omit<SelectProps, 'value' | 'name' | 'selectedOption' | 'options'> &
    Omit<FormFieldProps, 'errorText'> & {
        control: Control<T, object>;
        name: Path<T>;
        options: ReadonlyArray<SelectProps.Option>;
    };
