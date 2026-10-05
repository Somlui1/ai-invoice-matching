# Vendored PDF.js

Same-origin copy of the PDF.js generic build used by the optional **vector** render mode of the
page viewer (`js/viewer.js`).  It is committed on purpose: the portal runs on an intranet where a
public CDN may be unreachable, and the viewer must not depend on the internet.

| file | purpose |
|---|---|
| `pdf.min.mjs` | the library, imported as an ES module from `index.html` |
| `pdf.worker.min.mjs` | the parser worker, loaded by `GlobalWorkerOptions.workerSrc` |

* package: `pdfjs-dist`
* version: **4.10.38**
* licence: Apache-2.0 (see the licence header inside each file)
* obtained from: `https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/`

To upgrade, replace both files from the same release and reload the portal — nothing else in the
portal reads PDF.js internals.  If these files are deleted the viewer keeps working: it detects the
missing module and stays on server-rendered page rasters, which is the default mode anyway.
