import React from 'react';
import { Helmet } from 'react-helmet';
import cn from 'classnames';
import Button from 'components/Button';
import Tag from 'components/Tag';
import Header from './components/Header';
import RequestInvite from './RequestInvite';
import Connects from './Connects';
import Opportunities from './Opportunities';
import Footer from './components/Footer';
import { ReactComponent as ArrowRightIcon } from 'assets/icons/arrow-right.svg';
import { ReactComponent as CopyIcon } from 'assets/icons/content-copy.svg';
import pytorch from 'assets/icons/landing/pytorch.png';
import tensorflow from 'assets/icons/landing/tensorflow.png';
import wandb from 'assets/icons/landing/wandb.png';
import huggingface from 'assets/icons/landing/huggingface.png';
import fastapi from 'assets/icons/landing/fastapi_logo.png';
import streamlit from 'assets/icons/landing/streamlit_logo.png';
import gradio from 'assets/icons/landing/gradio_logo.png';
import jupyter from 'assets/icons/landing/jupyter_logo.png';
import microsoft from 'assets/icons/landing/microsoft-azure.png';
import aws from 'assets/icons/landing/aws.png';
import googleCloud from 'assets/icons/landing/google-cloud.png';
import pytorchLighning from 'assets/icons/landing/pytorch-lighning.png';
import ray from 'assets/icons/landing/ray.png';
import dask from 'assets/icons/landing/dask.svg';
import splash from 'assets/images/landing/splash.png';
import { tools, providers, plans } from './data';
import css from './index.module.css';
import { copyToClipboard } from 'libs';

const Landing: React.FC = () => {
    return (
        <div className={css.landing}>
            <Helmet>
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin={''} />
                <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@700&display=swap" rel="stylesheet" />
            </Helmet>

            {/*<div className={css.topLinks}>
                🚀 Read about interactive CLI, bash, and tensorboard providers! 🖖{' '}
                <a target="_blank" href="https://blog.dstack.ai/interactive-cli-bash-and-tensorboard-providers">
                    Learn more →
                </a>
            </div>*/}

            <Header />

            <main className={css.content}>
                <section className={css.section}>
                    <div className={css.container}>
                        <h1 className={css.sectionTitle}>Git-based CLI to run ML workflows on cloud</h1>

                        <div className={css.sectionText}>
                            dstack is an open-source tool that allows you to define ML workflows as code and run them on cloud.
                            dstack takes care of dependencies, infrastructure, and data management.
                        </div>

                        <RequestInvite className={css.firstInviteForm} />

                        {/*<div className={css.screenShot}>
                            <img width="1340" height="754" src={splash} alt="video splash" />
                        </div>*/}
                    </div>
                </section>

                <section className={css.section}>
                    <div className={css.container}>
                        <h2 className={css.sectionTitle}>Bringing GitOps to machine learning</h2>

                        <div className={css.sectionText}>
                            Instead of managing infrastructure yourself, writing custom scripts, or using cumbersome MLOps
                            platforms, define your workflows as code and run via the CLI.
                        </div>

                        <Opportunities className={css.opportunities} />
                    </div>
                </section>

                {/*<section className={css.section}>
                    <div className={css.container}>
                        <h2 className={css.sectionTitle}>Integration with developer tools</h2>

                        <div className={css.sectionText}>
                            Providers allow you to run a particular command, tool, application, or even dev environment in your
                            cloud account as if you did it locally.
                        </div>

                        <div className={css.providers}>
                            {providers.map((p, index) => (
                                <a href={`${p.url}`} target="_blank" className={cn(css.provider, css.withAmbreBg)} key={index}>
                                    <div className={cn(css.providerName)}>{p.name}</div>
                                    <div className={css.providerDesc}>{p.description}</div>
                                </a>
                            ))}

                            <a
                                href="https://docs.dstack.ai/providers/"
                                target="_blank"
                                className={css.allProviders}
                            >
                                More integrations
                                <ArrowRightIcon width={18} />
                            </a>
                        </div>
                    </div>
                </section>*/}

                <section className={css.section}>
                    <div className={css.container}>
                        <h2 className={css.sectionTitle}>Primary features of dstack</h2>

                        <div className={css.sectionText}>
                            dstack is an alternative to KubeFlow, SageMaker, Docker, SSH, custom scripts, and many other tools
                            used often to run ML workflows.
                        </div>

                        <div className={css.tools}>
                            {tools.map((o, index) => (
                                <div key={index} className={cn(css.tool, css.withAmbreBg)}>
                                    <h4 className={css.toolTitle}>{o.title}</h4>
                                    {o.text.split('\n').map((line, i) => (
                                        <p className={css.toolText} key={i}>
                                            {line}
                                        </p>
                                    ))}
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                {/*<section className={css.section}>
                    <div className={css.container}>
                        <h2 className={css.sectionTitle}>dstack Cloud Pricing</h2>


                        <div className={css.sectionText}>
                            Start small with the free plan and switch to the team plan as your team grows. For the on-premise
                            option and advanced features, contact our team.
                        </div>


                        <div className={css.plans}>
                            {plans.map((p) => (
                                <div className={css.plan} key={p.name}>
                                    <div className={css.planHead}>
                                        <div className={css.planTitle}>{p.title}</div>
                                        {p.price && <div className={css.planPrice}>{p.price}</div>}
                                    </div>

                                    <div className={css.planDesc}>{p.description}</div>

                                    <div className={css.planOpportunities}>
                                        {p.opportunities.map((o, index) => (
                                            <div key={index}>{o}</div>
                                        ))}
                                    </div>

                                    <hr />

                                    <div className={css.planProps}>
                                        {p.props.map((prop, index) => (
                                            <div className={css.planProp} key={index}>
                                                {prop.text} <span>{prop.value}</span>
                                            </div>
                                        ))}
                                    </div>

                                    {p.info && <div className={css.planInfo}>{p.info}</div>}

                                    {p.command && (
                                        <div className={css.planCommand}>
                                            {p.command}

                                            <Button
                                                className={css.planCommandCopy}
                                                appearance="blue-transparent"
                                                icon={<CopyIcon />}
                                                onClick={() => copyToClipboard(p.command ?? '')}
                                            />
                                        </div>
                                    )}

                                    <Button
                                        className={css.planButton}
                                        onClick={p.button.action}
                                        appearance={p.button.appearance}
                                        dimension="xl"
                                    >
                                        {p.button.title}
                                    </Button>
                                </div>
                            ))}
                        </div>

                        <h2 className={css.sectionTitle}>Extend your local terminal to the cloud</h2>

                        <div className={css.sectionText}>
                            Use the full power of the cloud but stay within your IDE or terminal.
                        </div>

                        <RequestInvite className={css.firstInviteForm} />

                        <div className={css.usedWithTitle}>Supports top frameworks, third-party tools, and cloud vendors</div>

                        <ul className={css.usedWithList}>
                            <li className={css.usedWithItem}>
                                <img src={pytorch} alt="PyTorch" height={24} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={pytorchLighning} alt="Lightning" height={30} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={tensorflow} alt="TensorFlow" height={47} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={streamlit} alt="Streamlit" height={43} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={gradio} alt="Gradio" height={33} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={fastapi} alt="FastAPI" height={40} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={jupyter} alt="Jupyter" height={24} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={huggingface} alt="HuggingFace" height={48} />
                            </li>
                            <li className={css.usedWithItem}>
                                <img src={dask} alt="Dask" height={29} />
                            </li>
                        </ul>
                    </div>
                </section>*/}

                <section className={css.section}>
                    <div className={css.container}>
                        <h2 className={css.sectionTitle}>Join our community</h2>

                        <div className={css.sectionText}>dstack is an open-source project with growing community.</div>

                        <Connects />
                    </div>
                </section>

                <Footer className={css.footer} />
            </main>
        </div>
    );
};

export default Landing;
