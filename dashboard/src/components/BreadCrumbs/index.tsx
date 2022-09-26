import React from 'react';
import cn from 'classnames';
import { Link, LinkProps } from 'react-router-dom';
import { ReactComponent as ChevronDownIcon } from 'assets/icons/chevron-down.svg';
import css from './index.module.css';

export interface Props extends Omit<React.HTMLAttributes<HTMLDivElement>, 'children'> {
    children: React.ReactElement<BreadcrumbItemProps> | Array<React.ReactElement<BreadcrumbItemProps>>;
}

const Breadcrumbs: React.FC<Props> = ({ children, className, ...props }) => {
    const arrayChildren = React.Children.toArray(children);

    return (
        <div className={cn(css.breadcrumbs, className)} {...props}>
            {React.Children.map(arrayChildren, (child, index) => {
                if (!React.isValidElement<BreadcrumbItemProps>(child)) {
                    throw new Error("It isn't BreadcrumbItem component");
                }

                const isLast = index === arrayChildren.length - 1;

                return (
                    <>
                        {child.props.to ? (
                            <Link className={css.link} to={child.props.to}>
                                {React.cloneElement(child, { isLast })}
                            </Link>
                        ) : (
                            React.cloneElement(child, { isLast })
                        )}

                        {!isLast && (
                            <span className={css.separator}>
                                <ChevronDownIcon />
                            </span>
                        )}
                    </>
                );
            })}
        </div>
    );
};

export interface BreadcrumbItemProps {
    to?: LinkProps['to'];
    children: string;
    isLast?: boolean;
}

const BreadcrumbItem: React.FC<BreadcrumbItemProps> = ({ children }) => {
    return <span className={css.item}>{children}</span>;
};

export default Object.assign(Breadcrumbs, { Item: BreadcrumbItem });
