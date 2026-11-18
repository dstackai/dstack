import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, IProps as ButtonProps } from '../Button';

export interface Props {
    visible: boolean;
    onChange: (visible: boolean) => void;
    variant?: ButtonProps['variant'];
    disabled?: boolean;
}

export const TokenVisibilityButton: React.FC<Props> = ({ visible, onChange, variant = 'normal', disabled }) => {
    const { t } = useTranslation();

    return (
        <Button formAction="none" variant={variant} disabled={disabled} wrapText={false} onClick={() => onChange(!visible)}>
            {visible ? t('common.hide_token') : t('common.show_token')}
        </Button>
    );
};
