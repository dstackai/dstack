import { ControllerProps, FieldValues } from 'react-hook-form';
import { CodeEditorProps } from '@cloudscape-design/components/code-editor';
import { FormFieldProps } from '@cloudscape-design/components/form-field';

export type FormCodeEditorProps<T extends FieldValues> = Omit<
    CodeEditorProps,
    'value' | 'name' | 'i18nStrings' | 'ace' | 'onPreferencesChange' | 'preferences'
> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'>;
