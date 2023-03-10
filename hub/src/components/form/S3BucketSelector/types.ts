import { ControllerProps, FieldValues } from 'react-hook-form';
import { FormFieldProps } from '@cloudscape-design/components/form-field';
import { S3ResourceSelectorProps } from '@cloudscape-design/components/s3-resource-selector';

export type FormS3BucketSelectorProps<T extends FieldValues> = Omit<
    S3ResourceSelectorProps,
    'resource' | 'fetchBuckets' | 'fetchVersions' | 'fetchObjects' | 'name'
> &
    Omit<FormFieldProps, 'errorText' | 'label'> &
    Pick<ControllerProps<T>, 'control' | 'name' | 'rules'> & {
        label: string;
        buckets: TAwsBucket[];
        disabled?: boolean;
    };
