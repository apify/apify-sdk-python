import React from 'react';
import clsx from 'clsx';
import Admonition from '@theme/Admonition';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import CodeBlock from '@theme/CodeBlock';
import ThemedImage from '@theme/ThemedImage';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './index.module.css';

import ApifyLogo from '@apify/docs-theme/static/img/apify_logo.svg';

function Hero() {
    return (
        <header className={clsx('container', styles.heroBanner)}>
            <div className="row padding-horiz--md">
                <div className="col col--7">
                    <div className={clsx(styles.relative, 'row')}>
                        <div className="col">
                            <h1 className={styles.tagline}>
                                Apify SDK for Python<br /> is a toolkit for<br /> building actors
                            </h1>
                            <h1 className={styles.tagline}>
                                Apify <span>SDK for Python</span><br /> is a toolkit for<br /> <span>building actors</span>
                            </h1>
                        </div>
                    </div>
                    <div className="row">
                        <div className="col">
                            <h2>Run Actors on the Apify platform directly from your Python code.</h2>
                        </div>
                    </div>
                    <div className="row">
                        <div className="col">
                            <div className={styles.heroButtons}>
                                <Link to="docs/guides" className={styles.getStarted}>Get Started</Link>
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
                            pip install apify
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
            title={`${siteConfig.title} · ${siteConfig.tagline}`}
            description={siteConfig.description}>
            <Hero />
        </Layout>
    );
}
