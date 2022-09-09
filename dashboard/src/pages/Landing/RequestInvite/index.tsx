import React from 'react';
import cn from 'classnames';
import Button from 'components/Button';
import css from './index.module.css';
import { ReactComponent as ArrowRightIcon } from 'assets/icons/arrow-right.svg';
import * as routes from 'routes';
import { useNavigate } from 'react-router-dom';
import { goToUrl } from 'libs';
import { ReactComponent as GithubCircleIcon } from 'assets/icons/github-circle.svg';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const RequestInvite: React.FC<Props> = ({ className }) => {
    /*const navigate = useNavigate();
    const toSignUp = () => {
        navigate(routes.signUp());
    };*/

    /*const goToDocs = () => {
        goToUrl('https://docs.dstack.ai/', true);
    };*/

    const goToDownload = () => {
        goToUrl('https://docs.dstack.ai/installation', true);
    };

    const goToGithub = () => {
        goToUrl('https://github.com/dstackai/dstack', true);
    };

    return (
        <div className={cn(css.requestInvite, className)}>
            <div className={css.buttons}>
                {/*<Button
                    type="submit"
                    appearance="blue-fill"
                    dimension="xxl"
                    direction="right"
                    className={css.button}
                    onClick={toSignUp}
                    icon={<ArrowRightIcon className={css.icon} width={16} />}
                >
                    Get started for free
                </Button>*/}

                <Button type="button" appearance="black-fill" dimension="xxl" className={css.button}
                        onClick={goToDownload}>
                    Download
                </Button>

                <Button
                    type="submit"
                    appearance="black-stroke"
                    dimension="xxl"
                    direction="right"
                    className={css.button}
                    onClick={goToGithub}
                >
                    <GithubCircleIcon className={css.gitHubIcon} /> GitHub
                </Button>

                {/*<Button type="button" appearance="black-stroke" dimension="xxl" className={css.button} onClick={goToGithub}>
                    <GithubCircleIcon className={css.gitHubIcon} /> Star us
                </Button>*/}
            </div>

            <div className={css.label}>
                Download the open source binary and run it locally in your environment
                {/*. See{' '}*/}
                {/*<a href={'https://docs.dstack.ai'} target={'_blank'}>*/}
                {/*    {' '}*/}
                {/*    how it works*/}
                {/*</a>*/}
                {/*.*/}
            </div>
        </div>
    );
};

export default RequestInvite;
