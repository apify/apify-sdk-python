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
    "comment": {
        "summary": [
            {
                "kind": "text",
                "text": "Apify SDK is a set of libraries that make it easy to build web crawlers and web scraping scripts that play nice with the Apify Platform. It provides a simple API for running actors and proxy management.\n\n It also provides a powerful data storage API for managing datasets, key-value stores, and request queues. The SDK is written in Python and runs on Python 3.8 and above. It is available on [PyPI](https://pypi.org/project/apify/)."
            },
        ]
    },
    "sources": [
        {
            "fileName": "src/index.ts",
            "line": 1,
            "character": 0,
            "url": "https://github.com/apify/apify-sdk-python/blob/123456/src/dummy.py"
        }
    ]
};

let oid = 1;

function getGroupName(object) {
    const groupPredicates = {
        'Errors': (x) => x.name.toLowerCase().includes('error'),
        'Async Resource Clients': (x) => x.name.toLowerCase().includes('async'),
        'Resource Clients': (x) => x.name.toLowerCase().includes('client'),
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
    'Resource Clients',
    'Async Resource Clients',
    'Helper Classes',
    'Enumerations',
    'Errors',
    'Constructors',
    'Methods',
    'Properties',
    'Enumeration Members'
];

const hidden = [
    '_BaseApifyClient',
    'BaseClient',
    'ActorJobBaseClient',
    'ResourceClient',
    'ResourceCollectionClient',
    '_BaseApifyClientAsync',
    'BaseClientAsync',
    'ActorJobBaseClientAsync',
    'ResourceClientAsync',
    'ResourceCollectionClientAsync'
]

const groupSort = (a, b) => groupsOrdered.indexOf(a.title) - groupsOrdered.indexOf(b.title);

// Taken from https://github.com/TypeStrong/typedoc/blob/v0.23.24/src/lib/models/reflections/kind.ts, modified
const kinds = {
    'class': {
        kind: 128,
        kindString: 'Class',
    },
    'function': {
        kind: 2048,
        kindString: "Method",
    },
    'data': {
        kind: 1024,
        kindString: 'Property',
    },
    'enum': {
        kind: 8,
        kindString: "Enumeration",
    },
    'enumValue': {
        kind: 16,
        kindString: "Enumeration Member",
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

function traverse(o, parent) {
    for( let x of o.members ?? []) {
        console.log(x.name);
        let typeDocType = kinds[x.type];

        if(x.bases?.includes('Enum')) {
            typeDocType = kinds['enum'];
        }

        let type = inferType(x.datatype);

        if(parent.kindString === 'Enumeration') {
            typeDocType = kinds['enumValue'];
            type = {
                type: 'literal',
                value: x.value,
            }
        }

        if(x.type in kinds && !hidden.includes(x.name)) {

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
                newObj.signatures = [{
                    id: oid++,
                    name: x.name,
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
                    parameters: x.args.map((p) => (p.name === 'self' ? undefined : {
                        id: oid++,
                        name: p.name,
                        kind: 32768,
                        kindString: 'Parameter',
                        flags: {
                            isOptional: p.datatype?.includes('Optional') ? 'true' : undefined,
                        },
                        type: inferType(p.datatype),
                        comment: x.docstring ? {
                            summary: [{
                                kind: 'text',
                                text: x.docstring?.content
                                    .slice((() =>{
                                        const i = x.docstring?.content.toLowerCase().search(p.name.toLowerCase());
                                        return i === -1 ? x.docstring?.content.length : i;
                                    })()).split('\n')[0].split('- ')[1],
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

            newObj.groups.sort(groupSort);
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

    fs.writeFileSync(path.join(__dirname, 'api-typedoc-generated.json'), JSON.stringify(acc, null, 2));
}

if (require.main === module) {
    main();
}

module.exports = {
    groupSort,
}