# TODO

- implement Phase 6 narrow generic browser updates;
- hot-update active stylesheet links by cache-busting/replacement without full document reload where safe;
- map directly referenced image/SVG/font assets to active views where reliable;
- emit typed `css-update` and `asset-update` events only for affected views;
- fall back from failed narrow browser updates to full reload;
- preserve coherent batching so one filesystem/build burst produces one externally visible update;
- keep JavaScript changes on the full-reload path; do not implement generic JS module HMR;
- add browser-client tests for successful narrow update and full-reload fallback;
- run `just check` and resolve any platform/toolchain issues exposed by Phase 5.
