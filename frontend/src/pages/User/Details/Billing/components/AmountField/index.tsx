import React from 'react';
import { FieldValues } from 'react-hook-form';

import { Box, FormInput } from 'components';
import { FormInputProps } from 'components/form/Input/types';

import styles from './styles.module.scss';

export type Props<T extends FieldValues> = Omit<FormInputProps<T>, 'leftContent' | 'type'>;

export const AmountField = <T extends FieldValues>(props: Props<T>) => {
    return (
        <div className={styles.amountInput}>
            <FormInput
                {...props}
                leftContent={
                    <div className={styles.prefix}>
                        <Box fontSize="heading-s" color="text-status-inactive">
                            $
                        </Box>
                    </div>
                }
                type="number"
            />
        </div>
    );
};
