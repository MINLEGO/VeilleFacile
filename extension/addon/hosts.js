// Shared classic script (background + options). Host permission pattern: no port, Firefox ignores it.
const hostPattern = (u) => { const x = new URL(u); return `${x.protocol}//${x.hostname}/*`; };
