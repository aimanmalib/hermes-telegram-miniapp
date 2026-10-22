// Replaces ./demo.ts in production builds (see vite.config.ts), so no sample
// data or demo code can end up in dist/ even as an unreferenced chunk.
export function handleDemoRequest(): never {
  throw new Error("demo mode is not part of this build");
}
