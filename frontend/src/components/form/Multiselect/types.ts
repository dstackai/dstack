import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { MultiselectProps } from '@cloudscape-design/components/multiselect';

export type FormMultiselectOption = MultiselectProps.Option;
export type FormMultiselectOptions = ReadonlyArray<FormMultiselectOption>;

export type FormMultiselectProps<T extends FieldValues> = Omit<
    MultiselectProps,
    'value' | 'name' | 'selectedOptions' | 'options'
> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'> & {
        options: ReadonlyArray<FormMultiselectOption>;
    };
