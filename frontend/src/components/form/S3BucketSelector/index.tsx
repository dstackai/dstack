import React, { useMemo, useRef } from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import cn from 'classnames';
import FormField from '@cloudscape-design/components/form-field';
import S3ResourceSelector from '@cloudscape-design/components/s3-resource-selector';
import { S3ResourceSelectorProps } from '@cloudscape-design/components/s3-resource-selector';

import { getResourceSelectorI18n } from './utils';

import { FormS3BucketSelectorProps } from './types';

import styles from './styles.module.scss';

export const FormS3BucketSelector = <T extends FieldValues>({
    name,
    rules,
    control,
    label,
    buckets: bucketsProp,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    onChange: onChangeProp,
    disabled,
    prefix = 's3://',
    i18nStrings,
    ...props
}: FormS3BucketSelectorProps<T>) => {
    const fetch = async () => Promise.resolve([]);
    const lastValue = useRef<string | null>(null);

    const buckets = useMemo<S3ResourceSelectorProps.Bucket[]>(() => {
        return bucketsProp.map((i) => ({
            Name: i.name,
            CreationDate: i.created,
            Region: i.region,
        }));
    }, [bucketsProp]);

    const fetchBuckets = (): Promise<S3ResourceSelectorProps.Bucket[]> => Promise.resolve(buckets);

    const customProps = {
        bucketsVisibleColumns: ['Name'],
        fetchBuckets: fetchBuckets,
        fetchObjects: fetch,
        fetchVersions: fetch,
        i18nStrings: getResourceSelectorI18n(prefix, i18nStrings),
    };

    return (
        <Controller
            name={name}
            control={control}
            rules={rules}
            render={({ field: { onChange, value, ...fieldRest }, fieldState: { error } }) => {
                const resource = { uri: value };
                const onChangeSelect: S3ResourceSelectorProps['onChange'] = (event) => {
                    const bucket = event.detail.resource.uri.replace(/^s3:\/\//, '');

                    if (lastValue.current === bucket) return;
                    lastValue.current = bucket;

                    onChange(bucket);
                    onChangeProp?.(event);
                };

                return (
                    <FormField
                        description={description}
                        label={label}
                        info={info}
                        stretch={stretch}
                        constraintText={constraintText}
                        secondaryControl={secondaryControl}
                        errorText={error?.message}
                    >
                        <div className={cn(styles.bucketSelector, { disabled })}>
                            <S3ResourceSelector
                                resource={resource}
                                onChange={onChangeSelect}
                                {...fieldRest}
                                {...props}
                                {...customProps}
                                invalid={!!error}
                            />
                        </div>
                    </FormField>
                );
            }}
        />
    );
};
