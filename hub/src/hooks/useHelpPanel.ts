import { openHelpPanel } from 'App/slice';

import useAppDispatch from './useAppDispatch';

import { THelpPanelContent } from 'App/types';

export const useHelpPanel = () => {
    const dispatch = useAppDispatch();

    const openPanel = (content: THelpPanelContent) => {
        dispatch(openHelpPanel(content));
    };

    return [openPanel];
};
