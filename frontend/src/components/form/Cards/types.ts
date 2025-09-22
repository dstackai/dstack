import { Control, FieldValues, Path } from 'react-hook-form';
import { CardsProps } from '@cloudscape-design/components/cards';

export type FormCardsProps<T extends FieldValues> = CardsProps & {
    control: Control<T, object>;
    name: Path<T>;
};
