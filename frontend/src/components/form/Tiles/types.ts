import { Control, FieldValues, Path } from 'react-hook-form';
import { TilesProps } from '@cloudscape-design/components/tiles';

export type FormTilesProps<T extends FieldValues> = Omit<TilesProps, 'value'> & {
    control: Control<T, object>;
    name: Path<T>;
};
