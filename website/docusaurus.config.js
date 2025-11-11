const path = require('path');

const { config } = require('@apify/docs-theme');

const { externalLinkProcessor } = require('./tools/utils/externalLink');

const GROUP_ORDER = [
    'Actor',
    'Charging',
    'Configuration',
    'Event data',
    'Event managers',
    'Events',
    'Request loaders',
    'Storage clients',
    'Storage data',
    'Storages',
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
    favicon: 'img/favicon.ico',
    scripts: ['/js/custom.js', ...(config.scripts ?? [])],
    githubHost: 'github.com',
    future: {
        experimental_faster: {
            // ssgWorkerThreads: true,
            swcJsLoader: true,
            swcJsMinimizer: true,
            swcHtmlMinimizer: true,
            lightningCssMinimizer: true,
            rspackBundler: true,
            mdxCrossCompilerCache: true,
            rspackPersistentCache: true,
        },
        v4: {
            removeLegacyPostBuildHeadAttribute: true,
            useCssCascadeLayers: false, // this breaks styles on homepage and link colors everywhere
        },
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
                    // Storages
                    {
                        url: 'https://crawlee.dev/python/api/class/Storage',
                        group: 'Storages',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/Dataset',
                        group: 'Storages',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/KeyValueStore',
                        group: 'Storages',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/RequestQueue',
                        group: 'Storages',
                    },
                    // Storage data
                    {
                        url: 'https://crawlee.dev/python/api/class/AddRequestsResponse',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/DatasetItemsListPage',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/DatasetMetadata',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/KeyValueStoreMetadata',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/KeyValueStoreRecord',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/KeyValueStoreRecordMetadata',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/ProcessedRequest',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/Request',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/RequestQueueMetadata',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/StorageMetadata',
                        group: 'Storage data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/ReqUnprocessedRequestuest',
                        group: 'Storage data',
                    },
                    // Event managers
                    {
                        url: 'https://crawlee.dev/python/api/class/EventManager',
                        group: 'Event managers',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/LocalEventManager',
                        group: 'Event managers',
                    },
                    // Events
                    {
                        url: 'https://crawlee.dev/python/api/enum/Event',
                        group: 'Events',
                    },
                    // Event data
                    {
                        url: 'https://crawlee.dev/python/api/class/EventAbortingData',
                        group: 'Event data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/EventExitData',
                        group: 'Event data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/EventMigratingData',
                        group: 'Event data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/EventPersistStateData',
                        group: 'Event data',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/EventSystemInfoData',
                        group: 'Event data',
                    },
                    // Storage clients
                    {
                        url: 'https://crawlee.dev/python/api/class/StorageClient',
                        group: 'Storage clients',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/MemoryStorageClient',
                        group: 'Storage clients',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/FileSystemStorageClient',
                        group: 'Storage clients',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/SqlStorageClient',
                        group: 'Storage clients',
                    },
                    // Request loaders
                    {
                        url: 'https://crawlee.dev/python/api/class/RequestLoader',
                        group: 'Request loaders',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/RequestManager',
                        group: 'Request loaders',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/RequestManagerTandem',
                        group: 'Request loaders',
                    },
                    {
                        url: 'https://crawlee.dev/python/api/class/SitemapRequestLoader',
                        group: 'Request loaders',
                    },
                ],
            },
        ],
        [
            '@signalwire/docusaurus-plugin-llms-txt',
            {
                content: {
                    includeVersionedDocs: false,
                    enableLlmsFullTxt: true,
                    includeBlog: true,
                    includeGeneratedIndex: false,
                    includePages: true,
                    relativePaths: false,
                },
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
    customFields: {
        ...(config.customFields ?? []),
    },
};
