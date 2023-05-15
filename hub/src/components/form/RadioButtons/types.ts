import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { RadioGroupProps } from '@cloudscape-design/components/radio-group';

export type FormRadioButtonsProps<T extends FieldValues> = Omit<RadioGroupProps, 'value' | 'name'> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'>;
