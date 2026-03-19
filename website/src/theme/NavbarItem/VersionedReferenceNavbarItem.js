import React from 'react';
import { useDocsVersionCandidates } from '@docusaurus/plugin-content-docs/client';
import DefaultNavbarItem from '@theme/NavbarItem/DefaultNavbarItem';

/* eslint-disable react/prop-types */
export default function VersionedReferenceNavbarItem({ docsPluginId, ...props }) {
    const [version] = useDocsVersionCandidates(docsPluginId);

    // Latest version → /reference, "current" (next) → /reference/next, others → /reference/{name}
    let to = '/reference';
    if (!version.isLast) {
        to = `/reference/${version.name === 'current' ? 'next' : version.name}`;
    }

    return <DefaultNavbarItem {...props} to={to} />;
}
