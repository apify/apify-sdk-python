/* eslint-disable global-require,import/no-extraneous-dependencies */
const { config } = require('@apify/docs-theme');
const { externalLinkProcessor } = require('./tools/utils/externalLink');
const { groupSort } = require('./transformDocs.js');

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
                            activeBaseRegex: 'docs(?!.*/changelog)',
                        },
                        {
                            to: 'api',
                            label: 'API',
                            position: 'left',
                            activeBaseRegex: 'sdk-python/(api|typedefs)(?!.*/changelog)',
                        },
                        {
                            to: 'docs/changelog',
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
        [
            'docusaurus-plugin-typedoc-api',
            {
                projectRoot: `.`,
                changelogs: false,
                readmes: false,
                packages: [{ path: '.' }],
                typedocOptions: {
                    excludeExternals: false,
                },
                pathToTypedocJSON: `${__dirname}/api-typedoc-generated.json`,
                sortSidebar: groupSort,
            },
        ],
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
