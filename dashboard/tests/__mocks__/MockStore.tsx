import React from 'react';
import { Provider } from 'react-redux';
import { store } from 'store';

type Props = {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    children: any;
};

const MockStore = ({ children }: Props) => {
    return <Provider store={store}>{children}</Provider>;
};

export default MockStore;
