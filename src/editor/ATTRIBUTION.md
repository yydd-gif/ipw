# GenOffice source attribution (Apache-2.0)

This product includes a **pinned source copy** of portions of
[genspark-ai/genoffice](https://github.com/genspark-ai/genoffice),
commit `09485f884dc845cf3bf27fb7edfe489f9d457aad` (2026-09-16).

Copyright 2026 Mainfunc, Inc. Licensed under the Apache License, Version 2.0.
See `vendor/genoffice/LICENSE` and `vendor/genoffice/NOTICE`.

Included here:

- `packages/docx-engine` (parse / paragraph-patch save)
- `packages/pptx-engine/custgeom` (workspace import of the engine)
- `packages/docx-engine/src/vendor/emf-converter` (Apache-2.0)

The official TipTap `apps/docs` UI is **not** shipped. Runtime npm packages used
by the engine (jszip, fast-xml-parser, utif2) are MIT / MIT-OR-GPL (jszip used
under MIT, matching upstream notices).

This software is **not** an Office replacement.
