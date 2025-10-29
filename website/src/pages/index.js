import React from 'react';
import clsx from 'clsx';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import CodeBlock from '@theme/CodeBlock';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './index.module.css';

import HomePageExample from '!!raw-loader!./home_page_example.py';

function Hero() {
    return (
        <header className={clsx('container', styles.heroBanner)}>
            <div className="row padding-horiz--md">
                <div className="col col--7">
                    <div className={clsx(styles.relative, 'row')}>
                        <div className="col">
                            <h1 className={styles.tagline}>
                                Apify SDK for Python<br /> is a toolkit for<br /> building Actors
                            </h1>
                            <h1 className={styles.tagline}>
                                <span>Apify SDK</span> for <span>Python</span><br /> is a <span>toolkit</span> for<br /> building <span>Actors</span>
                            </h1>
                        </div>
                    </div>
                    <div className="row">
                        <div className="col">
                            <h2></h2>
                            <h2>
                                The Apify SDK for Python is the official library for creating Apify Actors in Python. It provides useful features like Actor lifecycle management, local storage emulation, and Actor event handling.
                            </h2>
                        </div>
                    </div>
                    <div className="row">
                        <div className="col">
                            <div className={styles.heroButtons}>
                                <Link to="/docs/overview/introduction" className={styles.getStarted}>Get Started</Link>
                                <iframe src="https://ghbtns.com/github-btn.html?user=apify&repo=apify-sdk-python&type=star&count=true&size=large" frameBorder="0" scrolling="0" width="170" height="30" title="GitHub"></iframe>
                            </div>
                        </div>
                    </div>
                </div>
                <div className={clsx(styles.relative, 'col', 'col--5')}>
                    <div className={styles.logoBlur}>
                        <img src={useBaseUrl('img/logo-blur.png')} className={clsx(styles.hideSmall)} />
                    </div>
                    <div className={styles.codeBlock}>
                        <CodeBlock className="language-bash">
                            apify create my-python-actor
                        </CodeBlock>
                    </div>
                </div>
            </div>
        </header>
    );
}

export default function Home() {
    const { siteConfig } = useDocusaurusContext();
    return (
        <Layout
            description={siteConfig.description}>
            <Hero />
            <div>
                <div className="container">
                    <div className="row padding-horiz--md" >
                        <div className="col col--4">
                            <p style={{ lineHeight: '200%' }}>
                                For example, the Apify SDK makes it easy to read the Actor input with the <code>Actor.get_input()</code> method, and to save scraped data from your Actors to a dataset by simply using the <code>Actor.push_data()</code> method.
                            </p>
                        </div>
                        <div className="col col--8">
                            <CodeBlock className="language-python">{HomePageExample}</CodeBlock>
                        </div>
                    </div>
                </div>
            </div>
        </Layout>
    );
}
