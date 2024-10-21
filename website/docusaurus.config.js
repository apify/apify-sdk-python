/* eslint-disable global-require,import/no-extraneous-dependencies */
const { config } = require('@apify/docs-theme');
const { externalLinkProcessor } = require('./tools/utils/externalLink');
const { groupSort } = require('./transformDocs.js');

const { absoluteUrl } = config;

/** @type {Partial<import('@docusaurus/types').DocusaurusConfig>} */
module.exports = {
    title: 'SDK for Python | Apify Documentation',
    url: absoluteUrl,
    baseUrl: '/sdk/python',
    trailingSlash: false,
    organizationName: 'apify',
    projectName: 'apify-sdk-python',
    scripts: ['/js/custom.js'],
    favicon: 'img/favicon.ico',
    onBrokenLinks:
    /** @type {import('@docusaurus/types').ReportingSeverity} */ ('warn'),
    onBrokenMarkdownLinks:
    /** @type {import('@docusaurus/types').ReportingSeverity} */ ('warn'),
    themes: [
        [
            '@apify/docs-theme',
            {
                changelogFromRoot: true,
                subNavbar: {
                    title: 'SDK for Python',
                    items: [
                        {
                            to: 'docs/overview/introduction',
                            label: 'Docs',
                            position: 'left',
                            activeBaseRegex: '/docs(?!/changelog)',
                        },
                        {
                            to: '/reference',
                            label: 'Reference',
                            position: 'left',
                            activeBaseRegex: '/reference',
                        },
                        {
                            to: 'docs/changelog',
                            label: 'Changelog',
                            position: 'left',
                            activeBaseRegex: '/docs/changelog',
                        },
                        {
                            href: 'https://github.com/apify/apify-sdk-python',
                            label: 'GitHub',
                            position: 'left',
                        },
                    ],
                },
            },
        ],
    ],
    presets: /** @type {import('@docusaurus/types').PresetConfig[]} */ ([
        [
            '@docusaurus/preset-classic',
            /** @type {import('@docusaurus/preset-classic').Options} */
            ({
                docs: {
                    path: '../docs',
                    sidebarPath: './sidebars.js',
                    rehypePlugins: [externalLinkProcessor],
                    editUrl: 'https://github.com/apify/apify-sdk-python/edit/master/website/',
                },
                theme: {
                    customCss: require.resolve('./src/css/custom.css'),
                },
            }),
        ],
    ]),
    plugins: [
        [
            '@apify/docusaurus-plugin-typedoc-api',
            {
                projectRoot: '.',
                changelogs: false,
                readmes: false,
                packages: [{ path: '.' }],
                typedocOptions: {
                    excludeExternals: false,
                },
                pathToCurrentVersionTypedocJSON: `${__dirname}/api-typedoc-generated.json`,
                sortSidebar: groupSort,
                routeBasePath: 'reference',
                python: true,
            },
        ],
        ...config.plugins,
    ],
    themeConfig: {
        ...config.themeConfig,
        tableOfContents: {
            ...config.themeConfig.tableOfContents,
            maxHeadingLevel: 5,
        },
        image: 'https://docs.apify.com/sdk/python/img/docs-og.png',
    },
    staticDirectories: ['node_modules/@apify/docs-theme/static', 'static'],
};
