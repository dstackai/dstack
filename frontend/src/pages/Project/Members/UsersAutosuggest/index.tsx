import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Autosuggest, AutosuggestProps } from 'components';

import { useGetUserListQuery } from 'services/user';

export interface Props extends Omit<AutosuggestProps, 'value' | 'enteredTextLabel' | 'options'> {
    optionsFilter?: (options: AutosuggestOption[]) => AutosuggestOption[];
}

type AutosuggestOption = { value: string; label?: string };

export const UserAutosuggest: React.FC<Props> = ({ optionsFilter, onSelect: onSelectProp, ...props }) => {
    const { t } = useTranslation();
    const [value, setValue] = useState<string>('');
    const { data: usersData, isLoading: isUsersLoading } = useGetUserListQuery();

    const options: AutosuggestOption[] = useMemo(() => {
        if (!usersData) return [];

        return usersData.map((user) => ({
            value: user.username,
        }));
    }, [usersData]);

    const filteredOptions = optionsFilter ? optionsFilter(options) : options;

    const onSelectHandle: AutosuggestProps['onSelect'] = (args) => {
        if (onSelectProp && args.detail.value) onSelectProp(args);

        setValue('');
    };

    return (
        <Autosuggest
            value={value}
            enteredTextLabel={(text) => `${t('users_autosuggest.entered_text')} ${text}`}
            onChange={({ detail }) => setValue(detail.value)}
            options={filteredOptions}
            statusType={isUsersLoading ? 'loading' : undefined}
            loadingText={t('users_autosuggest.loading')}
            placeholder={t('users_autosuggest.placeholder')}
            empty={t('users_autosuggest.no_match')}
            onSelect={onSelectHandle}
            {...props}
        />
    );
};
