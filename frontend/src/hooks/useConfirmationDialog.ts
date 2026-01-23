import { close, open } from 'components/ConfirmationDialog/slice';
import { IProps as ConfirmationDialogProps } from 'components/ConfirmationDialog/types';

import { getUid } from '../libs';
import useAppDispatch from './useAppDispatch';

export const useConfirmationDialog = () => {
    const dispatch = useAppDispatch();

    const onDiscard = (uuid: string) => {
        dispatch(close(uuid));
    };

    const openConfirmationDialog = (props: Omit<ConfirmationDialogProps, 'onDiscard'>) => {
        const uuid = getUid();

        dispatch(
            open({
                uuid,
                ...props,
                onDiscard: () => onDiscard(uuid),
            }),
        );
    };

    return [openConfirmationDialog];
};
