import React from 'react';
import Link from '@docusaurus/Link';
import { useDocsVersion } from '@docusaurus/theme-common/internal';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

const ReferenceLink = ({ to, children }) => {
    const { version, isLast } = useDocsVersion();
    const { siteConfig } = useDocusaurusContext();

    let versionSlug;

    if (!version || siteConfig.presets[0][1].docs.disableVersioning) {
        versionSlug == '';
    } else if (version === 'current') {
        versionSlug = 'next/';
    } else if (isLast) {
        versionSlug = '';
    } else {
        versionSlug = `${version}/`;
    }

    return (
        <Link to={`/reference/${versionSlug}${to}`}><code>{children}</code></Link>
    );
};

export default ReferenceLink;
