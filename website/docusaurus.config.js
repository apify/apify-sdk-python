/* eslint-disable global-require,import/no-extraneous-dependencies */
const { config } = require('@apify/docs-theme');
const { externalLinkProcessor } = require('./tools/utils/externalLink');

const { absoluteUrl } = config;

/** @type {Partial<import('@docusaurus/types').DocusaurusConfig>} */
module.exports = {
    title: 'Apify Docs v2',
    tagline: 'Apify Documentation',
    url: absoluteUrl,
    baseUrl: '/sdk-python',
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
                subNavbar: {
                    title: 'SDK for Python',
                    items: [
                        {
                            type: 'doc',
                            docId: 'index',
                            label: 'Docs',
                            position: 'left',
                            activeBaseRegex: 'docs',
                        },
                        {
                            to: 'api/apify',
                            label: 'API',
                            position: 'left',
                            activeBaseRegex: 'sdk-python/(api|typedefs)(?!.*/changelog)',
                        },
                        {
                            to: '/changelog',
                            label: 'Changelog',
                            position: 'left',
                            activeBaseRegex: 'changelog',
                        },
                        // {
                        //     type: 'docsVersionDropdown',
                        //     position: 'left',
                        //     className: 'navbar__item', // fixes margin around dropdown - hackish, should be fixed in theme
                        //     dropdownItemsBefore: [],
                        //     dropdownItemsAfter: [],
                        // },
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
                    showLastUpdateAuthor: true,
                    showLastUpdateTime: true,
                    path: '../docs',
                    sidebarPath: './sidebars.js',
                    rehypePlugins: [externalLinkProcessor],
                },
            }),
        ],
    ]),
    plugins: [
        // [
        //     'docusaurus-plugin-typedoc-api',
        //     {
        //         projectRoot: `${__dirname}/..`,
        //         changelogs: true,
        //         readmes: true,
        //         sortPackages: (a, b) => {
        //             return packagesOrder.indexOf(a.packageName) - packagesOrder.indexOf(b.packageName);
        //         },
        //         packages: packages.map((name) => ({ path: `packages/${name}` })),
        //         typedocOptions: {
        //             excludeExternals: false,
        //         },
        //     },
        // ],
        // [
        //     'docusaurus-gtm-plugin',
        //     {
        //         id: 'GTM-TKBX678',
        //     },
        // ],
    ],
    themeConfig: config.themeConfig,
    staticDirectories: ['node_modules/@apify/docs-theme/static']
};
