import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import Tiles from '@cloudscape-design/components/tiles';
import { TilesProps } from '@cloudscape-design/components/tiles';

import { FormTilesProps } from './types';

export const FormTiles = <T extends FieldValues>({ name, control, onChange: onChangeProp, ...props }: FormTilesProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            render={({ field: { onChange, ...fieldRest } }) => {
                const onChangeSelect: TilesProps['onChange'] = (event) => {
                    onChange(event.detail.value);
                    onChangeProp && onChangeProp(event);
                };

                return <Tiles onChange={onChangeSelect} {...fieldRest} {...props} />;
            }}
        />
    );
};
