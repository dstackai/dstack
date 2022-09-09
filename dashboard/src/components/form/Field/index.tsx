import React from 'react';
import cn from 'classnames';
import { useTranslation } from 'react-i18next';
import { FieldError } from 'react-hook-form';
import css from './index.module.css';

export interface Props {
    className?: string;
    label?: string;
    children: React.ReactNode;
    error?: FieldError | string;
    notRequired?: boolean;
}

const isHookFormError = (error: FieldError | string): error is FieldError => {
    return typeof error !== 'string';
};

const Field: React.FC<Props> = ({ className, label, children, error, notRequired }) => {
    const { t } = useTranslation();

    const getFieldErrorText = (error: FieldError): string => {
        if (error.type === 'custom') return error.message ?? '';

        return t(`field_errors.${error.type}`);
    };

    return (
        <div className={cn(css.field, className)}>
            {label && (
                <div className={css.label}>
                    {label} {notRequired && <span className={css.optional}>({t('optional')})</span>}
                </div>
            )}
            {children}
            {error && <div className={css.error}>{isHookFormError(error) ? getFieldErrorText(error) : error}</div>}
        </div>
    );
};

export default Field;
