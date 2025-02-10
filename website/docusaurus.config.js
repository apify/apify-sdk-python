const path = require('path');

const { config } = require('@apify/docs-theme');

const { externalLinkProcessor } = require('./tools/utils/externalLink');

const GROUP_ORDER = [
    'Classes',
    'Data structures',
];

const groupSort = (g1, g2) => {
    if (GROUP_ORDER.includes(g1) && GROUP_ORDER.includes(g2)) {
        return GROUP_ORDER.indexOf(g1) - GROUP_ORDER.indexOf(g2);
    }
    return g1.localeCompare(g2);
};

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
    githubHost: 'github.com',
    future: {
        experimental_faster: true,
    },
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
                sortSidebar: groupSort,
                routeBasePath: 'reference',
                python: true,
                pythonOptions: {
                    pythonModulePath: path.join(__dirname, '../src/apify'),
                    moduleShortcutsPath: path.join(__dirname, '/module_shortcuts.json'),
                },
                reexports: [
                    {
                        url: 'https://crawlee.dev/python/api/class/Dataset',
                        group: 'Classes',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/KeyValueStore',
                        group: 'Classes',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/RequestQueue',
                        group: 'Classes',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/Request',
                        group: 'Classes',
                    },
                ],
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
