import type { FieldValues } from 'react-hook-form/dist/types/fields';
import type { UseFormReturn } from 'react-hook-form/dist/types/form';

export interface FleetFormFieldsProps<TFieldValues extends FieldValues = FieldValues>
    extends Pick<UseFormReturn<TFieldValues>, 'control'> {
    fieldNamePrefix?: string;
    disabledAllFields?: boolean;
}

export type FleetFormFields = {
    name?: string;
    min_instances: number;
    max_instances?: number;
    idle_duration?: string;
    spot_policy: TSpotPolicy;
};
