import React from 'react';
import Link from '@docusaurus/Link';

const ApiLink = ({ to, children }) => {
    return (
        <Link to={`/reference/${to}`}>{children}</Link>
    );
};

export default ApiLink;
