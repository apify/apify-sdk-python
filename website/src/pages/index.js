import React from 'react';
import clsx from 'clsx';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import CodeBlock from '@theme/CodeBlock';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import ProductHuntCard from '../components/ProductHuntCard';
import styles from './index.module.css';

function TopBanner() {
    const PHLogo = require('../../static/img/logo-ph.svg').default;
    const GHLogo = require('../../static/img/logo-gh.svg').default;
    return (
        <section className={clsx('container', styles.topBanner)}>
            <div className="row">
                <div className="col col--8">
                    <div className={clsx('container', styles.textRow)}>
                        <div className="row">
                            <h1>🎉 Apify SDK for Python is out!</h1>
                        </div>
                        <div className="row">
                            Check out the Apify SDK for Python on{' '}
                            <Link to="https://github.com/apify/apify-sdk-python">
                                <GHLogo className={styles.ghLogoSmall} />
                                GitHub
                            </Link>
                            &nbsp;and&nbsp;
                            <Link to="https://www.producthunt.com/posts/apify-python-sdk">
                                <PHLogo className={styles.phLogoSmall} />
                                Product Hunt
                            </Link>!
                        </div>
                    </div>
                </div>
                <div className={clsx('col col--4', styles.phcard)}>
                    <ProductHuntCard />
                </div>
            </div>
        </section>
    );
}

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
                                <span>Apify SDK</span> for <span>Python</span><br /> is a <span>toolkit</span> for<br /> building <span>actors</span>
                            </h1>
                        </div>
                    </div>
                    <div className="row">
                        <div className="col">
                            <h2></h2>
                            <h2>
                                The Apify SDK for Python is the official library for creating Apify Actors in Python.
                                It provides useful features like actor lifecycle management, local storage emulation, and actor event handling.
                            </h2>
                        </div>
                    </div>
                    <div className="row">
                        <div className="col">
                            <div className={styles.heroButtons}>
                                <Link to="docs/overview/introduction" className={styles.getStarted}>Get Started</Link>
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
            <TopBanner />
            <Hero />
            <div>
                <div className="container">
                    <div className="row padding-horiz--md" >
                        <div className="col col--4">
                            <p style={{ lineHeight: '200%' }}>
                            For example, the Apify SDK makes it easy to read the actor input with the <code>Actor.get_input()</code> method,
                            and to save scraped data from your actors to a dataset
                                {' '}by simply using the <code>Actor.push_data()</code> method.
                            </p>
                        </div>
                        <div className="col col--8">
                            <CodeBlock language='python'>{`from apify import Actor
from bs4 import BeautifulSoup
import requests

async def main():
    async with Actor:
        input = await Actor.get_input()
        response = requests.get(input['url'])
        soup = BeautifulSoup(response.content, 'html.parser')
        await Actor.push_data({ 'url': input['url'], 'title': soup.title.string })`
                            }</CodeBlock>
                        </div>
                    </div>
                </div>
            </div>
        </Layout>
    );
}
