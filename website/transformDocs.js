/* eslint-disable */

const fs = require('fs');
const path = require('path');

const acc = {
    'id': 0,
    'name': 'apify-sdk-python',
    'kind': 1,
    'kindString': 'Project',
    'flags': {},
    'originalName': '',
    'children': [],
    'groups': [],
    'sources': [
        {
            'fileName': 'src/index.ts',
            'line': 1,
            'character': 0,
            'url': 'https://github.com/apify/apify-sdk-python/blob/123456/src/dummy.py'
        }
    ]
};

let oid = 1;

function getGroupName(object) {
    const groupPredicates = {
        'Errors': (x) => x.name.toLowerCase().includes('error'),
        'Main Classes': (x) => ['actor', 'dataset', 'keyvaluestore', 'requestqueue'].includes(x.name.toLowerCase()),
        'Helper Classes': (x) => x.kindString === 'Class',
        'Methods': (x) => x.kindString === 'Method',
        'Constructors': (x) => x.kindString === 'Constructor',
        'Properties': (x) => x.kindString === 'Property',
        'Enumerations': (x) => x.kindString === 'Enumeration',
        'Enumeration Members': (x) => x.kindString === 'Enumeration Member',
    };

    const [group] = Object.entries(groupPredicates).find(
        ([_, predicate]) => predicate(object)
    );

    return group;
}

const groupsOrdered = [
    'Main Classes',
    'Helper Classes',
    'Errors',
    'Constructors',
    'Methods',
    'Properties',
    'Enumerations',
    'Enumeration Members'
];

const groupSort = (a, b) => {
    if(groupsOrdered.includes(a) && groupsOrdered.includes(b)){
        return groupsOrdered.indexOf(a) - groupsOrdered.indexOf(b)
    }
    return a.localeCompare(b);
};

// Taken from https://github.com/TypeStrong/typedoc/blob/v0.23.24/src/lib/models/reflections/kind.ts, modified
const kinds = {
    'class': {
        kind: 128,
        kindString: 'Class',
    },
    'function': {
        kind: 2048,
        kindString: 'Method',
    },
    'data': {
        kind: 1024,
        kindString: 'Property',
    },
    'enum': {
        kind: 8,
        kindString: 'Enumeration',
    },
    'enumValue': {
        kind: 16,
        kindString: 'Enumeration Member',
    },
}

function stripOptional(s) {
    return s ? s.replace(/Optional\[(.*)\]/g, '$1').replace('ListPage[Dict]', 'ListPage') : null;
}

function isCustomClass(s) {
    return !['dict', 'list', 'str', 'int', 'float', 'bool'].includes(s.toLowerCase());
}

function inferType(x) {
    return !isCustomClass(stripOptional(x) ?? '') ? {
        type: 'intrinsic',
        name: stripOptional(x) ?? 'void',
    } : {
        type: 'reference',
        name: stripOptional(x),
    }
}

function sortChildren(acc) {
    for (let group of acc.groups) {
        group.children
            .sort((a, b) => {
                const firstName = acc.children.find(x => x.id === a).name;
                const secondName = acc.children.find(x => x.id === b).name;
                return firstName.localeCompare(secondName);
            });
    }
    acc.groups.sort((a, b) => groupSort(a.title, b.title));
}

function parseArguments(docstring) {
    return (docstring
        .split('Args:')[1] ?? '').split('Returns:')[0]
        .split(/(^|\n)\s*([\w]+)\s*\(.*?\)\s*:\s*/)
        .filter(x => x.length > 1)
        .reduce((p,x,i,a) => {
            if(i%2 === 0){
                return {...p, [x]: a[i+1]}
            }
            return p;
        }, {}
    );
}

function isHidden(x) {
    return x.decorations?.some(d => d.name === 'ignore_docs') || x.name === 'ignore_docs' || !x.docstring?.content;
}

function traverse(o, parent) {
    for( let x of o.members ?? []) {
        let typeDocType = kinds[x.type];

        if(x.bases?.includes('Enum')) {
            typeDocType = kinds['enum'];
        }

        if (x.decorations?.some(d => d.name === 'dualproperty')) {
            typeDocType = kinds['data'];
        }

        let type = inferType(x.datatype);

        if(parent.kindString === 'Enumeration') {
            typeDocType = kinds['enumValue'];
            type = {
                type: 'literal',
                value: x.value,
            }
        }

        if(x.type in kinds && !isHidden(x)) {
            let newObj = {
                id: oid++,
                name: x.name,
                ...typeDocType,
                flags: {},
                comment: x.docstring ? {
                    summary: [{
                        kind: 'text',
                        text: x.docstring?.content,
                    }],
                } : undefined,
                type,
                children: [],
                groups: [],
            };

            if(newObj.kindString === 'Method') {
                const parameters = parseArguments(x.docstring?.content ?? '');

                newObj.signatures = [{
                    id: oid++,
                    name: x.name,
                    modifiers: x.modifiers ?? [],
                    kind: 4096,
                    kindString: 'Call signature',
                    flags: {},
                    comment: x.docstring ? {
                        summary: [{
                            kind: 'text',
                            text: x.docstring?.content
                                .replace(/\**(Args|Arguments|Returns)[\s\S]+/, ''),
                        }],
                    } : undefined,
                    type: inferType(x.return_type),
                    parameters: x.args.map((p) => ((p.name === 'self' || p.name === 'cls') ? undefined : {
                        id: oid++,
                        name: p.name,
                        kind: 32768,
                        kindString: 'Parameter',
                        flags: {
                            isOptional: p.datatype?.includes('Optional') ? 'true' : undefined,
                        },
                        type: inferType(p.datatype),
                        comment: parameters[p.name] ? {
                            summary: [{
                                kind: 'text',
                                text: parameters[p.name]
                            }]
                        } : undefined,
                    })).filter(x => x),
                }];
            }

            if(newObj.name === '__init__') {
                newObj.kindString = 'Constructor';
                newObj.kind = 512;
            }

            traverse(x, newObj);

            const groupName = getGroupName(newObj);

            const group = parent.groups.find((g) => g.title === groupName);
            if(group) {
                group.children.push(newObj.id);
            } else {
                parent.groups.push({
                    title: groupName,
                    children: [newObj.id],
                });
            }

            sortChildren(newObj);
            parent.children.push(newObj);
        }
    }
}

function main() {
    const argv = process.argv.slice(2);

    const rawdump = fs.readFileSync(argv[0], 'utf8');
    const modules = rawdump.split('\n').filter((line) => line !== '');

    for (const module of modules) {
        const o = JSON.parse(module);

        traverse(o, acc);
    };

    // recursively fix references (collect names->ids of all the named entities and then inject those in the reference objects)
    const names = {};
    function collectIds(o) {
        for (const child of o.children ?? []) {
            names[child.name] = child.id;
            collectIds(child);
        }
    }
    collectIds(acc);

    function fixRefs(o) {
        for (const child of o.children ?? []) {
            if (child.type?.type === 'reference') {
                child.type.id = names[child.type.name];
            }
            if (child.signatures) {
                for (const sig of child.signatures) {
                    for (const param of sig.parameters ?? []) {
                        if (param.type?.type === 'reference') {
                            param.type.id = names[param.type.name];
                        }
                    }
                    if (sig.type?.type === 'reference') {
                        sig.type.id = names[sig.type.name];
                    }
                }
            }
            fixRefs(child);
        }
    }
    fixRefs(acc);
    sortChildren(acc);

    fs.writeFileSync(path.join(__dirname, 'api-typedoc-generated.json'), JSON.stringify(acc, null, 2));
}

if (require.main === module) {
    main();
}

module.exports = {
    groupSort,
}
