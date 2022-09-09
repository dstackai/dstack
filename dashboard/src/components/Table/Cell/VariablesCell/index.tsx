import React, { useMemo } from 'react';
import { ITableVariablesCell } from 'components/Table/types';
import cn from 'classnames';
import Variable from 'components/Variable';
import Button from 'components/Button';
import { useAppDispatch } from 'hooks';
import { showVariablesModal } from 'features/VariablesModal/slice';
import css from './index.module.css';
import { variablesToArray } from 'libs';

export interface Props extends Pick<ITableVariablesCell, 'data'> {
    children?: React.ReactNode;
}

const VariablesCell: React.FC<Props> = ({ children, data }) => {
    const dispatch = useAppDispatch();
    const variables = useMemo<IVariable[]>(() => variablesToArray(data), [data]);
    const [first, ...other] = variables;

    const onClick = (event: React.MouseEvent<HTMLButtonElement | HTMLDivElement>) => {
        // For not open run table item collapsable list
        event.stopPropagation();
        dispatch(showVariablesModal(variables));
    };

    if (!first) return null;

    return (
        <div className={cn(css.variables)}>
            <Variable className={css.variable} variable={first} onClick={onClick} />

            {Boolean(other.length) && (
                <Button onClick={onClick} className={css.otherCount} appearance="blue-transparent" dimension="s">
                    <span>+{other.length}</span>
                </Button>
            )}
            {children}
        </div>
    );
};

export default VariablesCell;
