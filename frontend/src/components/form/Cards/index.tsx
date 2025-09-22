import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import Cards from '@cloudscape-design/components/cards';
import { CardsProps } from '@cloudscape-design/components/cards';

import { FormCardsProps } from './types';

export const FormCards = <T extends FieldValues>({
    name,
    control,
    onSelectionChange: onSelectionChangeProp,
    ...props
}: FormCardsProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            render={({ field: { onChange, ...fieldRest } }) => {
                const onSelectionChange: CardsProps['onSelectionChange'] = (event) => {
                    onChange(event.detail.selectedItems.map(({ value }) => value));
                    onSelectionChangeProp?.(event);
                };

                const selectedItems = props.items.filter((item) => fieldRest.value?.includes(item.value));

                return (
                    <Cards
                        onSelectionChange={onSelectionChange}
                        trackBy="value"
                        {...fieldRest}
                        {...props}
                        selectedItems={selectedItems}
                    />
                );
            }}
        />
    );
};
