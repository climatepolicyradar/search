// k6/experimental/tracing was removed by Grafana; its drop-in replacement is
// the http-instrumentation-tempo jslib, imported by URL below. @types/k6@2.2.0
// (the latest published version) has no declarations for that URL module, so
// every script that imports it fails `tsc --noEmit` in CI's Lint job. Minimal
// ambient shim covering the one export actually used across these scripts
// (`instrumentHTTP`), typed against
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
declare module "https://jslib.k6.io/http-instrumentation-tempo/1.0.1/index.js" {
  interface InstrumentHTTPOptions {
    propagator: "w3c" | "b3";
  }

  interface Tracing {
    instrumentHTTP(options: InstrumentHTTPOptions): void;
  }

  const tracing: Tracing;
  export default tracing;
}
