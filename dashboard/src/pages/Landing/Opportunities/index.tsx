import React from 'react';
import cn from 'classnames';
import { opportunities } from './data';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const Opportunities: React.FC<Props> = ({ className, ...props }) => {
    return (
        <div className={cn(className)} {...props}>
            {opportunities.map((o, index) => (
                <div className={cn(css.item, css[o.align])} key={index}>
                    <div className={css.asset}>{o.asset}</div>

                    <div className={css.details}>
                        <div className={css.title}>{o.title}</div>

                        {o.points.map((p, pIndex) => (
                            <div className={css.point} key={pIndex}>
                                <div className={css.pointTitle}>{p.title}</div>
                                <div className={css.pointText}>
                                    {p.text.split('\n').map((line, i) => (
                                        <p key={i}>{line}</p>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );
};

export default Opportunities;
