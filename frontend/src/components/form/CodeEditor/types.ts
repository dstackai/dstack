import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';

import { CodeEditorProps } from '../../CodeEditor';

export type FormCodeEditorProps<T extends FieldValues> = Omit<
    CodeEditorProps,
    'value' | 'name' | 'i18nStrings' | 'ace' | 'onPreferencesChange' | 'preferences'
> &
    Omit<FormFieldProps, 'errorText'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'>;
