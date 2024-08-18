import React from 'react';
import { useTranslation } from 'react-i18next';
import Link from '@cloudscape-design/components/link';

import { IProps } from './types';

export const InfoLink: React.FC<IProps> = (props) => {
    const { t } = useTranslation();

    return (
        <Link {...props} variant="info">
            {t('common.info')}
        </Link>
    );
};
