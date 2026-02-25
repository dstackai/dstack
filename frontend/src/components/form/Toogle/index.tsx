import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import ToggleCSD from '@cloudscape-design/components/toggle';

import { FormToggleProps } from './types';

import styles from './index.module.scss';

export const FormToggle = <T extends FieldValues>({
    name,
    control,
    rules,
    defaultValue,
    label,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    leftContent,
    toggleLabel,
    onChange: onChangeProp,
    toggleDescription,
    toggleInfo,
    errorText: externalErrorText,
    ...props
}: FormToggleProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            rules={rules}
            defaultValue={defaultValue}
            render={({ field: { onChange, value, ...fieldRest }, fieldState: { error } }) => {
                return (
                    <FormField
                        description={description}
                        label={label}
                        info={info}
                        stretch={stretch}
                        constraintText={constraintText}
                        secondaryControl={secondaryControl}
                        errorText={error?.message || externalErrorText}
                    >
                        {leftContent}

                        <ToggleCSD
                            {...fieldRest}
                            {...props}
                            checked={value}
                            onChange={(event) => {
                                onChange(event.detail.checked);
                                onChangeProp?.(event);
                            }}
                            description={toggleDescription}
                        >
                            {(toggleLabel || toggleInfo) && (
                                <span className={styles.labelWithInfo}>
                                    {toggleLabel}
                                    {toggleLabel && toggleInfo && <span aria-hidden="true" className={styles.divider} />}
                                    {toggleInfo && (
                                        <span
                                            className={styles.info}
                                            onClick={(e) => e.stopPropagation()}
                                            onMouseDown={(e) => e.stopPropagation()}
                                            onPointerDown={(e) => e.stopPropagation()}
                                            onKeyDown={(e) => e.stopPropagation()}
                                        >
                                            {toggleInfo}
                                        </span>
                                    )}
                                </span>
                            )}
                        </ToggleCSD>
                    </FormField>
                );
            }}
        />
    );
};
