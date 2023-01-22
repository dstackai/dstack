import React from 'react';
import css from './index.module.css';

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    return (
        <div className={css.layout}>
            <div>Dstack</div>
            <div>{children}</div>
        </div>
    );
};

export default AppLayout;
