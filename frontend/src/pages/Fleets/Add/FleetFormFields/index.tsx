import React from 'react';
import { useTranslation } from 'react-i18next';

import { FormInput, InfoLink, SpaceBetween } from 'components';

import { useHelpPanel } from 'hooks';

import { FLEET_IDLE_DURATION_INFO, FLEET_MAX_INSTANCES_INFO, FLEET_MIN_INSTANCES_INFO } from './constants';
import { FleetFormFieldsProps } from './type';

import type { FieldValues } from 'react-hook-form/dist/types/fields';

export function FleetFormFields<T extends FieldValues = FieldValues>({
    control,
    disabledAllFields,
    fieldNamePrefix,
}: FleetFormFieldsProps<T>) {
    const { t } = useTranslation();
    const [openHelpPanel] = useHelpPanel();

    const getFieldNameWitPrefix = (name: string) => {
        if (!fieldNamePrefix) {
            return name;
        }

        [fieldNamePrefix, name].join('.');
    };

    return (
        <SpaceBetween direction="vertical" size="l">
            <FormInput
                label={t('fleets.edit.name')}
                placeholder={t('fleets.edit.name_placeholder')}
                constraintText={t('fleets.edit.name_constraint')}
                control={control}
                //eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                name={getFieldNameWitPrefix(`name`)}
                disabled={disabledAllFields}
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(FLEET_MIN_INSTANCES_INFO)} />}
                label={t('fleets.edit.min_instances')}
                constraintText={t('fleets.edit.min_instances_description')}
                control={control}
                //eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                name={getFieldNameWitPrefix(`min_instances`)}
                disabled={disabledAllFields}
                type="number"
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(FLEET_MAX_INSTANCES_INFO)} />}
                label={t('fleets.edit.max_instances')}
                constraintText={t('fleets.edit.max_instances_description')}
                placeholder={t('fleets.edit.max_instances_placeholder')}
                control={control}
                //eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                name={getFieldNameWitPrefix(`max_instances`)}
                disabled={disabledAllFields}
                type="number"
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(FLEET_IDLE_DURATION_INFO)} />}
                label={t('fleets.edit.idle_duration')}
                constraintText={t('fleets.edit.idle_duration_description')}
                control={control}
                //eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                name={getFieldNameWitPrefix(`idle_duration`)}
                disabled={disabledAllFields}
            />
        </SpaceBetween>
    );
}
