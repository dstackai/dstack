import React from 'react';
import Button from 'components/Button';
import cn from 'classnames';
import slack from 'assets/images/landing/slack.png';
import slackHighRes from 'assets/images/landing/slack@2x.png';
import dstack from 'assets/images/landing/small-logo.svg';
import css from './index.module.css';
import { goToUrl } from '../../../libs';
import MailchimpSubscribe from "../MailchimpSubscribe";

export type Props = React.HTMLAttributes<HTMLDivElement>;

const Connects: React.FC<Props> = ({ className, ...props }) => {
    return (
        <div className={cn(css.connects, className)} {...props}>
            <div className={css.item}>
                <div className={css.icon}>
                    <img width={38} height={38} src={slack} srcSet={`${slackHighRes} 2x`} alt="slack icon" />
                </div>

                <div className={css.title}>Slack chat</div>
                <div className={css.text}>
                    Join the&nbsp;Slack chat to ask questions and get help from other users.{' '}
                </div>

                <Button
                    className={css.button}
                    appearance="black-fill"
                    dimension="xxl"
                    onClick={() =>
                        goToUrl('https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ', true)
                    }
                >
                    Join Slack
                </Button>
            </div>

            <div className={css.item}>
                <div className={css.icon}>
                    <img width={38} height={38} src={dstack} alt="dstack icon" />
                </div>

                <div className={css.title}>Mailing list</div>
                <div className={css.text}>
                    Subscribe to the mailing list to get notified about major product updates.
                </div>

                <MailchimpSubscribe />
            </div>
        </div>
    );
};

export default Connects;
