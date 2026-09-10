// @types/k6@2.2.0 (the latest published version) has no declarations for
// k6/experimental/tracing, so every script that imports it fails `tsc
// --noEmit` in CI's Lint job. Minimal ambient shim covering the one export
// actually used across these scripts (`instrumentHTTP`), typed against
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
declare module "k6/experimental/tracing" {
  interface InstrumentHTTPOptions {
    propagator: "w3c" | "b3";
  }

  function instrumentHTTP(options: InstrumentHTTPOptions): void;

  const _default: { instrumentHTTP: typeof instrumentHTTP };
  export default _default;
}
